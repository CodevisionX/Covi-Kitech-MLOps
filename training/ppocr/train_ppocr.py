"""PP-OCRv6 medium 숫자 인식 학습 (플랫폼 작업용 진입점).

흐름: 데이터 다운로드 -> 라벨 검사 -> 학습(학습/검증 지표 MLflow 기록)
      -> Validation 기준 체크포인트 선택 -> Validation/Test 평가 -> 내보내기 -> 모델 기록

데이터 구조(DATASET_PATH = 'bucket/prefix'):
  {train,val[,test]}_list.txt  각 줄: '<이미지 상대경로>\\t<정답 문자열>'
  images/...                   목록이 가리키는 이미지

학습 설정은 PaddleOCR 공식 PP-OCRv6_medium_rec.yml 에 고객 학습 설정을 덮어쓴 값입니다.
각 값은 같은 이름의 대문자 환경 변수로 바꿀 수 있습니다.
"""
import json
import os
import re
import subprocess
import sys
import traceback
from copy import deepcopy
from pathlib import Path

import mlflow
import yaml
from mlflow.models import ModelSignature
from mlflow.types import ColSpec, Schema

from dataset_tools import read_rec_list, validate_recognition
from mlops_common import (
    JOB_ID, WORK_DIR, dataset_manifest, download_dataset, env_float, env_int,
    env_str, environment_info, job_tags, logger, package_versions, report_status,
    sha256_file, verify_registered_manifest,
)

ENGINE = Path(os.getenv("PADDLEOCR_ROOT", "/opt/PaddleOCR"))
BASE_CONFIG = ENGINE / "configs/rec/PP-OCRv6/PP-OCRv6_medium_rec.yml"
DICT_PATH = ENGINE / "ppocr/utils/dict/ppocrv6_dict.txt"
PACKAGES = ["paddlepaddle-gpu", "numpy", "opencv-python", "albumentations", "mlflow"]

TRAIN_LINE = re.compile(r"epoch: \[(\d+)/\d+\], global_step: (\d+), (.*?), avg_reader_cost")
CUR_METRIC = re.compile(r"cur metric, (.*)")
KV = re.compile(r"([A-Za-z_]+): (-?[\d.]+(?:e-?\d+)?)")


# ---------------------------------------------------------------- 데이터
def check_labels(root: Path, lists_dir: Path) -> dict:
    """등록 때와 같은 규칙으로 다시 검사하고, BOM 을 지운 목록 사본을 lists_dir 에 씁니다."""
    charset = set(DICT_PATH.read_text(encoding="utf-8").splitlines())
    stats, rep = validate_recognition(root, charset=charset, check_images=False)
    if rep.n_errors:
        raise ValueError("데이터셋 검사 실패:\n" + "\n".join(rep.errors[:20]))
    for w in rep.warnings[:20]:
        logger.warning(w)
    lists_dir.mkdir(parents=True, exist_ok=True)
    for split in stats["counts"]:
        lines = read_rec_list(root / f"{split}_list.txt")
        (lists_dir / f"{split}_list.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stats["counts"]


# ---------------------------------------------------------------- 설정
def build_config(data_dir: Path, lists_dir: Path, out_dir: Path) -> dict:
    cfg = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    batch = env_int("BATCH", 32)
    workers = env_int("WORKERS", 4)
    g = cfg["Global"]
    g.update(
        use_gpu=env_str("DEVICE", "gpu") == "gpu",
        epoch_num=env_int("EPOCHS", 50),
        max_text_length=env_int("MAX_TEXT_LENGTH", 8),
        save_epoch_step=env_int("SAVE_EPOCH_STEP", 1),
        eval_batch_step=[0, env_int("EVAL_BATCH_STEP", 50)],
        distributed=False,
        seed=env_int("SEED", 1024),
        pretrained_model=str(Path(os.getenv("PRETRAINED_DIR", "/opt/pretrained"))
                             / "PP-OCRv6_medium_rec_pretrained.pdparams"),
        checkpoints=None,
        save_model_dir=str(out_dir / "fit"),
        save_inference_dir=str(out_dir / "inference"),
        save_res_path=str(out_dir / "predictions.txt"),
        character_dict_path=str(DICT_PATH),
    )
    lr = cfg["Optimizer"]["lr"]
    lr["learning_rate"] = env_float("LEARNING_RATE", 0.0001)
    lr["warmup_epoch"] = env_int("WARMUP_EPOCH", 2)

    train, ev = cfg["Train"], cfg["Eval"]
    train["dataset"].update(data_dir=str(data_dir), label_file_list=[str(lists_dir / "train_list.txt")],
                            ratio_list=[1.0])
    train["loader"].update(batch_size_per_card=batch, drop_last=False, num_workers=workers)
    if "sampler" in train:
        train["sampler"]["first_bs"] = batch
    ev["dataset"].update(data_dir=str(data_dir), label_file_list=[str(lists_dir / "val_list.txt")])
    ev["loader"].update(batch_size_per_card=env_int("EVAL_BATCH", 64), num_workers=workers)
    return cfg


def write_config(cfg: dict, path: Path) -> Path:
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------- 엔진 실행
def run_engine(tool: str, config: Path, extra=(), on_line=None) -> list:
    cmd = [sys.executable, str(ENGINE / "tools" / tool), "-c", str(config), *extra]
    logger.info("실행: %s", " ".join(cmd))
    env = dict(os.environ, FLAGS_use_mkldnn="0", PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT="0",
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    lines = []
    with subprocess.Popen(cmd, cwd=ENGINE, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                          errors="replace", bufsize=1) as proc:
        for line in proc.stdout:
            sys.stdout.write(line)
            lines.append(line.rstrip("\n"))
            if on_line:
                on_line(line)
        code = proc.wait()
    if code != 0:
        raise RuntimeError(f"{tool} 실패 (exit {code})")
    return lines


class TrainLogParser:
    """train.py 출력에서 학습/검증 지표를 읽어 MLflow 에 기록합니다."""

    def __init__(self):
        self.step = 0

    def __call__(self, line):
        try:
            m = TRAIN_LINE.search(line)
            if m:
                self.step = int(m.group(2))
                metrics = {f"train/{k}": float(v) for k, v in KV.findall(m.group(3))}
                metrics["train/epoch"] = float(m.group(1))
                mlflow.log_metrics(metrics, step=self.step)
                return
            m = CUR_METRIC.search(line)
            if m:
                metrics = {f"val/{k}": float(v) for k, v in KV.findall(m.group(1))
                           if k != "fps"}
                mlflow.log_metrics(metrics, step=self.step)
        except Exception as e:
            logger.warning("지표 기록 실패(학습은 계속): %s", e)


def parse_eval(lines: list) -> dict:
    """eval.py 의 'metric eval ***' 뒤 'key:value' 줄을 읽습니다."""
    out, started = {}, False
    for line in lines:
        if "metric eval" in line:
            started = True
            continue
        if started:
            m = re.search(r"INFO: ([A-Za-z_]+):(-?[\d.]+(?:e-?\d+)?)\s*$", line)
            if m:
                out[m.group(1)] = float(m.group(2))
    if "acc" not in out:
        raise RuntimeError("평가 결과(acc)를 읽지 못했습니다")
    return out


def evaluate(cfg: dict, ckpt: str, split: str, lists_dir: Path, out_dir: Path) -> dict:
    c = deepcopy(cfg)
    c["Global"]["pretrained_model"] = ckpt
    c["Eval"]["dataset"]["label_file_list"] = [str(lists_dir / f"{split}_list.txt")]
    path = write_config(c, out_dir / f"eval_{split}.yml")
    metrics = parse_eval(run_engine("eval.py", path))
    # 학습 중 step 별 val/* 와 구분하기 위해 최종 검증 결과는 best_val/* 로 기록
    prefix = "best_val" if split == "val" else split
    return {f"{prefix}/{k}": v for k, v in metrics.items() if k != "fps"}


# ---------------------------------------------------------------- 메인
def main():
    run_id = os.getenv("MLFLOW_RUN_ID")
    if not run_id:
        logger.error("MLFLOW_RUN_ID 가 없습니다.")
        sys.exit(1)

    logger.info("--- [START] PP-OCRv6 인식 학습 | Job %s ---", JOB_ID)
    data_dir = WORK_DIR / "data"
    lists_dir = WORK_DIR / "lists"
    out_dir = WORK_DIR / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))

    with mlflow.start_run(run_id=run_id):
        try:
            # 1. 데이터 준비 및 검사
            dataset_path = os.getenv("DATASET_PATH", "")
            download_dataset(dataset_path, data_dir)
            counts = check_labels(data_dir, lists_dir)
            logger.info("데이터 검사 통과: %s", counts)
            manifest = dataset_manifest(data_dir)
            verify_registered_manifest(manifest)

            # 2. 설정 생성 및 실행 정보 기록
            cfg = build_config(data_dir, lists_dir, out_dir)
            train_cfg = write_config(cfg, out_dir / "config.yml")
            g = cfg["Global"]
            if job_tags():
                mlflow.set_tags(job_tags())
            mlflow.set_tags({
                "task": "recognition",
                "model_family": "PP-OCRv6_medium_rec",
                "dataset_path": dataset_path,
                "dataset_sha256": manifest["sha256"],
            })
            mlflow.log_params({
                "epochs": g["epoch_num"],
                "batch": cfg["Train"]["loader"]["batch_size_per_card"],
                "eval_batch": cfg["Eval"]["loader"]["batch_size_per_card"],
                "workers": cfg["Train"]["loader"]["num_workers"],
                "learning_rate": cfg["Optimizer"]["lr"]["learning_rate"],
                "warmup_epoch": cfg["Optimizer"]["lr"]["warmup_epoch"],
                "max_text_length": g["max_text_length"],
                "eval_batch_step": g["eval_batch_step"][1],
                "seed": g["seed"],
                "device": "gpu" if g["use_gpu"] else "cpu",
                "pretrained_weights": Path(g["pretrained_model"]).name,
                "pretrained_sha256": sha256_file(Path(g["pretrained_model"])),
                "dataset_sha256": manifest["sha256"],
                "dataset_file_count": manifest["file_count"],
                **{f"n_{s}_samples": n for s, n in counts.items()},
            })
            mlflow.log_dict(manifest, "dataset/manifest.json")
            mlflow.log_dict({"counts": counts}, "dataset/summary.json")
            env_info = environment_info(PACKAGES)
            env_info["paddleocr_commit"] = os.getenv("PADDLEOCR_COMMIT")
            mlflow.log_dict(env_info, "environment.json")
            mlflow.log_artifact(str(train_cfg), artifact_path="config")

            # 3. 학습
            run_engine("train.py", train_cfg, on_line=TrainLogParser())

            # 4. Validation 기준 체크포인트 선택
            #    검증 정확도가 한 번도 오르지 않으면(예: 매우 짧은 학습) best_accuracy 가 없으므로 latest 사용
            fit = out_dir / "fit"
            if (fit / "best_accuracy.pdparams").is_file():
                ckpt, selection = str(fit / "best_accuracy"), "best_val_acc"
            elif (fit / "latest.pdparams").is_file():
                ckpt, selection = str(fit / "latest"), "latest_fallback"
                logger.warning("best_accuracy 체크포인트가 없어 latest 를 사용합니다.")
            else:
                raise FileNotFoundError("학습 체크포인트가 없습니다")
            mlflow.set_tag("checkpoint_selection", selection)

            # 5. 선택된 체크포인트로 Validation / Test 평가
            final = evaluate(cfg, ckpt, "val", lists_dir, out_dir)
            if "test" in counts:
                final.update(evaluate(cfg, ckpt, "test", lists_dir, out_dir))
            else:
                logger.warning("test_list.txt 가 없어 Test 평가를 건너뜁니다.")
                mlflow.set_tag("test_split", "missing")
            mlflow.log_metrics(final)
            logger.info("최종 평가: %s", json.dumps(final, ensure_ascii=False))

            # 6. 내보내기 (현장 프로그램이 읽는 inference.json / .pdiparams / .yml)
            run_engine("export_model.py", train_cfg,
                       extra=["-o", f"Global.pretrained_model={ckpt}"])
            inference_dir = out_dir / "inference"
            for name in ("inference.json", "inference.pdiparams", "inference.yml"):
                if not (inference_dir / name).is_file():
                    raise FileNotFoundError(f"내보내기 결과가 없습니다: {name}")
            mlflow.log_param("model_sha256", sha256_file(inference_dir / "inference.pdiparams"))

            # 7. 아티팩트와 모델 기록 (체크포인트 전체는 크므로 선택된 것만)
            mlflow.log_artifact(f"{ckpt}.pdparams", artifact_path="checkpoint")
            for f in ("train.log", "config.yml"):
                if (fit / f).is_file():
                    mlflow.log_artifact(str(fit / f), artifact_path="training")
            here = Path(__file__).resolve().parent
            paddle_ver = package_versions(["paddlepaddle-gpu"])["paddlepaddle-gpu"]
            mlflow.pyfunc.log_model(
                name="model",
                python_model=str(here / "ppocr_pyfunc.py"),
                artifacts={"inference_dir": str(inference_dir)},
                signature=ModelSignature(inputs=Schema([ColSpec("string", "image")])),
                pip_requirements=[f"paddlepaddle-gpu=={paddle_ver}", "opencv-python",
                                  "numpy", "PyYAML"],
            )

            report_status("FINISHED", "Training completed successfully.")
            logger.info("--- [DONE] ---")
        except Exception as e:
            logger.error("학습 실패:\n%s", traceback.format_exc())
            mlflow.end_run(status="FAILED")
            report_status("FAILED", str(e))
            sys.exit(1)


if __name__ == "__main__":
    main()
