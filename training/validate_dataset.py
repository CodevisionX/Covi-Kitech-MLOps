"""데이터셋 등록 검사 작업 (백엔드가 컨테이너로 실행, GPU 불필요).

흐름: 임시 업로드 영역(_staging) 다운로드 -> zip 풀기/정리 -> 작업 종류별 검사
      -> 매니페스트(파일별 sha256) 작성 -> 등록 위치에 업로드 -> 임시 영역 삭제 -> 백엔드 보고

환경 변수
  DATASET_VERSION_ID  백엔드 DB 의 데이터셋 버전 id
  DATASET_TASK        detection | recognition
  STAGING_PATH        bucket/_staging/<업로드 id>
  TARGET_PATH         bucket/registered/.../v<N>   (데이터는 그 아래 data/, 매니페스트는 manifest.json)
"""
import json
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from dataset_tools import (
    check_split_leakage, detection_split, normalize_upload, recognition_split_map,
    validate_detection, validate_recognition,
)
from mlops_common import (
    BACKEND_URL, WORK_DIR, _s3_client, dataset_manifest, download_dataset, env_int, logger,
)

VERSION_ID = os.getenv("DATASET_VERSION_ID", "")
DICT_PATH = Path(os.getenv("PADDLEOCR_ROOT", "/opt/PaddleOCR")) / "ppocr/utils/dict/ppocrv6_dict.txt"


def split_path(path: str):
    bucket, prefix = path.strip("/").split("/", 1)
    return bucket, prefix.rstrip("/") + "/"


def list_keys(s3, bucket, prefix):
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys += [o["Key"] for o in page.get("Contents", [])]
    return keys


def delete_keys(s3, bucket, keys):
    for i in range(0, len(keys), 1000):
        s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]], "Quiet": True})


def report(status, **payload):
    try:
        r = requests.post(f"{BACKEND_URL}/api/v1/datasets/versions/{VERSION_ID}/complete",
                          json={"status": status, **payload}, timeout=30)
        logger.info("[Webhook] %s | HTTP %s", status, r.status_code)
    except Exception as e:
        logger.error("[Webhook] 연결 실패: %s", e)


def main():
    task = os.getenv("DATASET_TASK")
    staging, target = os.getenv("STAGING_PATH", ""), os.getenv("TARGET_PATH", "")
    logger.info("--- [START] 데이터셋 검사 | 버전 %s | %s ---", VERSION_ID, task)
    s3 = _s3_client()
    t_bucket, t_prefix = split_path(target)
    uploaded = []
    try:
        if task not in ("detection", "recognition"):
            raise ValueError(f"알 수 없는 작업 종류: {task}")
        if list_keys(s3, t_bucket, t_prefix):
            raise RuntimeError(f"등록 위치가 비어 있지 않습니다(덮어쓰기 금지): {target}")

        # 1. 받기 및 정리
        raw = WORK_DIR / "upload"
        download_dataset(staging, raw)
        root = normalize_upload(raw)
        logger.info("데이터셋 루트: %s", root.relative_to(raw).as_posix() or ".")

        # 2. 검사
        if task == "detection":
            stats, rep = validate_detection(root)
            split_of = detection_split
        else:
            charset = set(DICT_PATH.read_text(encoding="utf-8").splitlines()) if DICT_PATH.is_file() else None
            stats, rep = validate_recognition(root, charset=charset,
                                              max_text_length=env_int("MAX_TEXT_LENGTH", 8))
            split_map = recognition_split_map(root)
            split_of = split_map.get
        manifest = dataset_manifest(root)
        check_split_leakage(manifest["files"], split_of, rep)
        summary = rep.summary()
        logger.info("검사 결과: 오류 %d건, 경고 %d건", summary["error_count"], len(summary["warnings"]))
        for m in summary["errors"][:20]:
            logger.error("  %s", m)
        for m in summary["warnings"][:20]:
            logger.warning("  %s", m)
        if summary["error_count"]:
            report("FAILED", message=f"검사 오류 {summary['error_count']}건", stats=stats, report=summary)
            sys.exit(1)

        # 3. 등록 위치에 업로드 (검사·해시한 바로 그 파일을 올림)
        files = sorted(manifest["files"])
        logger.info("등록 위치에 업로드: s3://%s/%s (%d개, %.1f MB)", t_bucket, t_prefix,
                    len(files), manifest["total_bytes"] / 1e6)

        def put(rel):
            key = f"{t_prefix}data/{rel}"
            s3.upload_file(str(root / rel), t_bucket, key)
            return key

        with ThreadPoolExecutor(max_workers=16) as pool:
            for i, key in enumerate(pool.map(put, files), 1):
                uploaded.append(key)
                if i % 1000 == 0 or i == len(files):
                    logger.info("  업로드 %d/%d", i, len(files))
        doc = {**manifest, "task": task, "stats": stats, "report": summary}
        for name, body in (("manifest.json", doc), ("report.json", {"stats": stats, "report": summary})):
            s3.put_object(Bucket=t_bucket, Key=t_prefix + name, ContentType="application/json",
                          Body=json.dumps(body, ensure_ascii=False, indent=1).encode("utf-8"))
            uploaded.append(t_prefix + name)

        # 4. 임시 영역 정리
        if not env_int("KEEP_STAGING", 0):
            s_bucket, s_prefix = split_path(staging)
            delete_keys(s3, s_bucket, list_keys(s3, s_bucket, s_prefix))

        report("READY", stats=stats, report=summary, manifest_sha256=manifest["sha256"],
               file_count=manifest["file_count"], total_bytes=manifest["total_bytes"])
        logger.info("--- [DONE] 등록 완료: %s ---", manifest["sha256"][:12])
    except SystemExit:
        raise
    except Exception as e:
        logger.error("데이터셋 검사 실패:\n%s", traceback.format_exc())
        if uploaded:  # 일부만 올라간 등록 데이터는 지움
            try:
                delete_keys(s3, t_bucket, uploaded)
            except Exception:
                logger.error("부분 업로드 정리 실패: %s", traceback.format_exc())
        report("FAILED", message=str(e)[:2000])
        sys.exit(1)


if __name__ == "__main__":
    main()
