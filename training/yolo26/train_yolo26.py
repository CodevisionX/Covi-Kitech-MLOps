"""YOLO26 숫자 그룹 검출 학습 (플랫폼 작업용 진입점).

흐름: 데이터 다운로드 -> 구조 검사 -> 학습(에폭별 지표 MLflow 기록)
      -> Validation 기준 best.pt 선택 -> Validation/Test 평가 -> 모델 기록

데이터 구조(DATASET_PATH = 'bucket/prefix'):
  images/{train,val[,test]}/*.png|jpg   labels/{train,val[,test]}/*.txt (YOLO 형식)
  dataset.yaml 또는 data.yaml (선택, names 만 사용)

기본 학습 설정은 고객 학습 코드와 같습니다. 각 값은 같은 이름의 대문자 환경 변수로 바꿀 수 있습니다.
"""
import json
import os
import sys
import traceback
from pathlib import Path

import mlflow
import yaml
from mlflow.models import ModelSignature
from mlflow.types import ColSpec, ParamSchema, ParamSpec, Schema

from mlops_common import (
    JOB_ID, WORK_DIR, dataset_manifest, download_dataset, env_float, env_int,
    env_str, environment_info, job_tags, logger, package_versions, report_status,
    sanitize_metric_name, sha256_file,
)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp"}
PACKAGES = ["ultralytics", "torch", "torchvision", "numpy", "opencv-python", "mlflow"]


def train_options(data_yaml: Path, project: Path) -> dict:
    return dict(
        data=str(data_yaml),
        epochs=env_int("EPOCHS", 100),
        imgsz=env_int("IMGSZ", 640),
        batch=env_int("BATCH", 8),
        workers=env_int("WORKERS", 4),
        device=env_str("DEVICE", "0"),
        patience=env_int("PATIENCE", 20),
        seed=env_int("SEED", 42),
        deterministic=True,
        pretrained=True,
        degrees=env_float("DEGREES", 2.0),
        translate=env_float("TRANSLATE", 0.03),
        scale=env_float("SCALE", 0.10),
        fliplr=env_float("FLIPLR", 0.0),
        flipud=env_float("FLIPUD", 0.0),
        perspective=env_float("PERSPECTIVE", 0.0005),
        mosaic=env_float("MOSAIC", 0.2),
        project=str(project),
        name="fit",
        exist_ok=True,
        plots=True,
    )


def check_dataset(root: Path) -> dict:
    """이미지마다 라벨이 있고 라벨 형식이 맞는지 검사하고, 분할별 개수를 돌려줍니다."""
    names = {0: "number_group"}
    for cand in ("dataset.yaml", "data.yaml"):
        if (root / cand).is_file():
            loaded = yaml.safe_load((root / cand).read_text(encoding="utf-8")) or {}
            if loaded.get("names"):
                raw = loaded["names"]
                names = dict(enumerate(raw)) if isinstance(raw, list) else {int(k): v for k, v in raw.items()}
            break
    nc = len(names)

    counts = {}
    for split in ("train", "val", "test"):
        img_dir = root / "images" / split
        if not img_dir.is_dir():
            if split in ("train", "val"):
                raise FileNotFoundError(f"필수 폴더가 없습니다: images/{split}")
            continue
        images = [p for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS]
        if not images:
            raise ValueError(f"이미지가 없습니다: images/{split}")
        boxes = 0
        for img in images:
            label = root / "labels" / split / (img.stem + ".txt")
            if not label.is_file():
                raise FileNotFoundError(f"라벨 파일이 없습니다: {label.relative_to(root)}")
            for n, line in enumerate(label.read_text(encoding="utf-8-sig").splitlines(), 1):
                if not line.strip():
                    continue
                parts = line.split()
                ok = len(parts) == 5
                if ok:
                    try:
                        cls = int(parts[0])
                        vals = [float(v) for v in parts[1:]]
                        ok = 0 <= cls < nc and all(0.0 <= v <= 1.0 for v in vals)
                    except ValueError:
                        ok = False
                if not ok:
                    raise ValueError(f"라벨 형식 오류: {label.relative_to(root)}:{n}: {line!r}")
                boxes += 1
        counts[split] = {"images": len(images), "boxes": boxes}
    return {"names": names, "counts": counts}


def evaluate(weights: Path, data_yaml: Path, split: str, opts: dict, out: Path) -> dict:
    from ultralytics import YOLO

    res = YOLO(str(weights)).val(
        data=str(data_yaml), split=split, imgsz=opts["imgsz"], batch=opts["batch"],
        device=opts["device"], workers=opts["workers"], plots=True,
        project=str(out), name=f"eval_{split}", exist_ok=True, verbose=False,
    )
    # 학습 중 에폭별 val/* 와 구분하기 위해 최종 검증 결과는 best_val/* 로 기록
    prefix = "best_val" if split == "val" else split
    return {
        f"{prefix}/precision": float(res.box.mp),
        f"{prefix}/recall": float(res.box.mr),
        f"{prefix}/mAP50": float(res.box.map50),
        f"{prefix}/mAP50-95": float(res.box.map),
    }


def on_fit_epoch_end(trainer):
    """에폭(학습+검증)이 끝날 때마다 학습 손실, 검증 지표, 학습률을 기록합니다."""
    metrics = {
        **trainer.label_loss_items(trainer.tloss, prefix="train"),
        **(trainer.metrics or {}),
        **(trainer.lr or {}),
    }
    clean = {sanitize_metric_name(k): float(v) for k, v in metrics.items()}
    try:
        mlflow.log_metrics(clean, step=trainer.epoch + 1)
    except Exception as e:
        logger.warning("에폭 지표 기록 실패(학습은 계속): %s", e)


def main():
    run_id = os.getenv("MLFLOW_RUN_ID")
    if not run_id:
        logger.error("MLFLOW_RUN_ID 가 없습니다.")
        sys.exit(1)

    logger.info("--- [START] YOLO26 검출 학습 | Job %s ---", JOB_ID)
    data_dir = WORK_DIR / "data"
    out_dir = WORK_DIR / "runs"
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))

    with mlflow.start_run(run_id=run_id):
        try:
            # 1. 데이터 준비 및 검사
            dataset_path = os.getenv("DATASET_PATH", "")
            download_dataset(dataset_path, data_dir)
            info = check_dataset(data_dir)
            logger.info("데이터 검사 통과: %s", info["counts"])
            manifest = dataset_manifest(data_dir)

            data_yaml = WORK_DIR / "dataset.yaml"
            spec = {"path": data_dir.as_posix(), "train": "images/train", "val": "images/val",
                    "names": info["names"]}
            if "test" in info["counts"]:
                spec["test"] = "images/test"
            data_yaml.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")

            # 2. 실행 정보 기록 (재현용)
            opts = train_options(data_yaml, out_dir)
            weights = Path(os.getenv("PRETRAINED_DIR", "/opt/pretrained")) / env_str("PRETRAINED_WEIGHTS", "yolo26n.pt")
            if job_tags():
                mlflow.set_tags(job_tags())
            mlflow.set_tags({
                "task": "detection",
                "model_family": "YOLO26",
                "dataset_path": dataset_path,
                "dataset_sha256": manifest["sha256"],
            })
            mlflow.log_params({k: v for k, v in opts.items() if k not in ("data", "project", "name", "exist_ok")})
            mlflow.log_params({
                "pretrained_weights": weights.name,
                "pretrained_sha256": sha256_file(weights),
                "dataset_sha256": manifest["sha256"],
                "dataset_file_count": manifest["file_count"],
                **{f"n_{s}_images": c["images"] for s, c in info["counts"].items()},
            })
            mlflow.log_dict(manifest, "dataset/manifest.json")
            mlflow.log_dict({"names": info["names"], "counts": info["counts"]}, "dataset/summary.json")
            mlflow.log_dict(environment_info(PACKAGES), "environment.json")

            # 3. 학습 (ultralytics 자체 MLflow 연동은 끄고 우리 콜백으로 기록)
            from ultralytics import YOLO, settings as yolo_settings
            yolo_settings.update({"mlflow": False})
            model = YOLO(str(weights))
            model.add_callback("on_fit_epoch_end", on_fit_epoch_end)
            model.train(**opts)

            # 4. Validation 기준 체크포인트 선택 (ultralytics 가 검증 fitness 최고 에폭을 best.pt 로 저장)
            weights_dir = out_dir / "fit" / "weights"
            best = weights_dir / "best.pt"
            selection = "best_val_fitness"
            if not best.is_file():
                best = weights_dir / "last.pt"
                selection = "last_fallback"
            if not best.is_file():
                raise FileNotFoundError("학습 결과 가중치(best.pt/last.pt)가 없습니다")
            mlflow.set_tags({"checkpoint_selection": selection})

            # 5. 선택된 모델로 Validation / Test 평가
            final = evaluate(best, data_yaml, "val", opts, out_dir)
            if "test" in info["counts"]:
                final.update(evaluate(best, data_yaml, "test", opts, out_dir))
            else:
                logger.warning("Test 분할(images/test)이 없어 Test 평가를 건너뜁니다.")
                mlflow.set_tag("test_split", "missing")
            mlflow.log_metrics(final)
            logger.info("최종 평가: %s", json.dumps(final, ensure_ascii=False))

            # 6. 아티팩트와 모델 기록
            mlflow.log_artifacts(str(out_dir), artifact_path="training")
            mlflow.log_param("model_sha256", sha256_file(best))
            here = Path(__file__).resolve().parent
            mlflow.pyfunc.log_model(
                name="model",
                python_model=str(here / "yolo26_pyfunc.py"),
                artifacts={"weights": str(best)},
                # 서명이 없으면 MLflow 가 예측 시 params(conf, imgsz)를 무시하므로 명시
                signature=ModelSignature(
                    inputs=Schema([ColSpec("string", "image")]),
                    params=ParamSchema([ParamSpec("conf", "float", 0.25),
                                        ParamSpec("imgsz", "long", opts["imgsz"])]),
                ),
                pip_requirements=[
                    f"ultralytics=={package_versions(['ultralytics'])['ultralytics']}",
                    "torch", "torchvision", "opencv-python", "numpy",
                ],
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
