"""YOLO26 / PP-OCR 학습 이미지가 함께 쓰는 공통 기능.

- 백엔드가 넘겨주는 환경 변수 읽기
- RustFS(S3) 데이터셋 병렬 다운로드
- 데이터/모델 해시, 실행 환경(라이브러리, GPU) 기록
- 백엔드 완료 웹훅 호출
"""
import hashlib
import importlib.metadata as md
import json
import logging
import os
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3
import requests
from botocore.config import Config

os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
os.environ.setdefault("MLFLOW_PYTHON_IGNORE_GIT_ERROR", "true")

JOB_ID = os.getenv("JOB_ID", "unknown")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
# 컨테이너 내부 작업 폴더. 결과물은 MLflow(RustFS)에 남기므로 컨테이너와 함께 지워져도 됩니다.
WORK_DIR = Path(os.getenv("WORK_DIR", "/work"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("mlops")


# ---------------------------------------------------------------- 환경 변수
def env_int(name, default):
    v = os.getenv(name)
    return int(v) if v not in (None, "") else default


def env_float(name, default):
    v = os.getenv(name)
    return float(v) if v not in (None, "") else default


def env_str(name, default):
    v = os.getenv(name)
    return v if v not in (None, "") else default


def job_tags():
    try:
        tags = json.loads(os.getenv("JOB_TAGS", "{}") or "{}")
        return tags if isinstance(tags, dict) else {}
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------- 데이터셋
def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("MLFLOW_S3_ENDPOINT_URL", "http://rustfs:9000"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        config=Config(s3={"addressing_style": "path"}, max_pool_connections=32),
    )


def download_dataset(dataset_path: str, local_dir: Path, workers: int = 16) -> Path:
    """'bucket/prefix' 아래 파일을 local_dir 로 병렬 다운로드합니다.

    대용량(수십 GB) 데이터셋을 고려해 여러 파일을 동시에 받습니다.
    """
    if not dataset_path or "/" not in dataset_path.strip("/"):
        raise ValueError(f"DATASET_PATH 형식은 'bucket/prefix' 여야 합니다: {dataset_path!r}")
    bucket, prefix = dataset_path.strip("/").split("/", 1)
    prefix = prefix.rstrip("/") + "/"  # 'a' 가 'ab/' 까지 받는 일을 막음

    s3 = _s3_client()
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith("/"):
                keys.append((obj["Key"], obj["Size"]))
    if not keys:
        raise FileNotFoundError(f"데이터셋이 비어 있거나 없습니다: s3://{bucket}/{prefix}")

    total = sum(size for _, size in keys)
    logger.info("데이터셋 다운로드: s3://%s/%s -> %s (%d개, %.1f MB)",
                bucket, prefix, local_dir, len(keys), total / 1e6)

    local_dir = local_dir.resolve()

    def fetch(key):
        target = (local_dir / key[len(prefix):]).resolve()
        if not target.is_relative_to(local_dir):
            raise ValueError(f"잘못된 객체 경로: {key}")
        target.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, key, str(target))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, _ in enumerate(pool.map(fetch, [k for k, _ in keys]), 1):
            if i % 500 == 0 or i == len(keys):
                logger.info("  다운로드 %d/%d", i, len(keys))
    return local_dir


# ---------------------------------------------------------------- 해시 / 환경 정보
def sha256_file(path: Path, chunk=1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def dataset_manifest(root: Path) -> dict:
    """폴더 안 모든 파일의 sha256 목록과 전체 해시(파일 목록+해시를 이은 값의 sha256)."""
    files = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            files[p.relative_to(root).as_posix()] = sha256_file(p)
    digest = hashlib.sha256(
        "".join(f"{k}\t{v}\n" for k, v in files.items()).encode()
    ).hexdigest()
    return {"sha256": digest, "file_count": len(files), "files": files}


def package_versions(names) -> dict:
    out = {}
    for n in names:
        try:
            out[n] = md.version(n)
        except md.PackageNotFoundError:
            out[n] = None
    return out


def gpu_info() -> list:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return [line.strip() for line in r.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def environment_info(packages) -> dict:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": package_versions(packages),
        "gpus": gpu_info(),
        "cuda_flavor": os.getenv("CUDA_FLAVOR"),
    }


# ---------------------------------------------------------------- MLflow 보조
def sanitize_metric_name(name: str) -> str:
    """MLflow 지표 이름에 쓸 수 없는 괄호를 정리합니다. 예: metrics/mAP50(B) -> metrics/mAP50_B"""
    return name.replace("(", "_").replace(")", "").replace(" ", "_")


# ---------------------------------------------------------------- 백엔드 웹훅
def report_status(status: str, message: str = ""):
    if not JOB_ID or JOB_ID == "unknown":
        return
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/v1/jobs/{JOB_ID}/complete",
            json={"status": status, "message": message[:2000]},
            timeout=10,
        )
        logger.info("[Webhook] %s | HTTP %s", status, resp.status_code)
    except Exception as e:
        logger.error("[Webhook] 연결 실패: %s", e)
