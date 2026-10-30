"""현장에서 쓰던 모델 파일을 학습 결과와 같은 형식의 MLflow run 으로 기록합니다.

가져온 모델은 새로 학습한 모델과 똑같이 서빙, E2E 평가, 배포 패키지에 쓸 수 있어
"현장 모델 대비 나아졌는가"를 같은 평가 데이터로 비교할 수 있습니다.

환경 변수
  MLFLOW_RUN_ID   백엔드가 만든 run
  MODEL_VARIANT   YOLO26 | PP-OCRv6
  IMPORT_PATH     올린 파일이 있는 'bucket/prefix'
  IMGSZ           검출 입력 크기 (기본 640)
"""
import base64
import json
import os
import sys
import traceback

import mlflow
import numpy as np
import pandas as pd

from mlops_common import (JOB_ID, WORK_DIR, _s3_client, download_dataset, env_int,
                          environment_info, job_tags, logger, report_status, sha256_file)

REC_FILES = ("inference.json", "inference.pdiparams", "inference.yml")


def blank_png(w: int, h: int) -> str:
    import cv2
    ok, buf = cv2.imencode(".png", np.full((h, w, 3), 255, np.uint8))
    return base64.b64encode(buf.tobytes()).decode()


def prepare_detection(root):
    from ultralytics import YOLO

    weights = sorted(root.rglob("*.pt"))
    if len(weights) != 1:
        raise ValueError(f"검출 모델은 .pt 파일 1개가 필요합니다 (찾음: {[w.name for w in weights]})")
    w = weights[0]
    model = YOLO(str(w))
    if model.task != "detect":
        raise ValueError(f"검출(detect) 모델이 아닙니다: task={model.task}")
    names = model.names if isinstance(model.names, dict) else dict(enumerate(model.names))
    mlflow.set_tags({"task": "detection", "model_family": "YOLO26"})
    mlflow.log_params({"model_sha256": sha256_file(w), "imported_file": w.name,
                       "n_classes": len(names), "imgsz": env_int("IMGSZ", 640)})
    mlflow.log_dict({"names": {int(k): v for k, v in names.items()}}, "dataset/summary.json")

    from train_yolo26 import PACKAGES, log_detection_model
    log_detection_model(w, env_int("IMGSZ", 640))
    return PACKAGES, blank_png(640, 640)


def prepare_recognition(root):
    found = {name: sorted(root.rglob(name)) for name in REC_FILES}
    bad = {k: len(v) for k, v in found.items() if len(v) != 1}
    if bad:
        raise ValueError(f"인식 모델은 {', '.join(REC_FILES)} 가 1개씩 필요합니다 (개수: {bad})")
    dirs = {v[0].parent for v in found.values()}
    if len(dirs) != 1:
        raise ValueError("inference.* 파일 3개는 같은 폴더에 있어야 합니다")
    inference_dir = dirs.pop()
    mlflow.set_tags({"task": "recognition", "model_family": "PP-OCRv6"})
    mlflow.log_params({"model_sha256": sha256_file(inference_dir / "inference.pdiparams"),
                       "imported_file": ",".join(REC_FILES)})

    from train_ppocr import PACKAGES, log_recognition_model
    log_recognition_model(inference_dir)
    return PACKAGES, blank_png(320, 48)


def cleanup(import_path: str):
    bucket, prefix = import_path.strip("/").split("/", 1)
    s3 = _s3_client()
    keys = [{"Key": o["Key"]} for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix=prefix.rstrip("/") + "/") for o in page.get("Contents", [])]
    if keys:
        s3.delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})


def safe_cleanup(import_path: str):
    # 완료를 보고하면 백엔드가 컨테이너를 바로 지우므로 보고 전에 정리합니다
    try:
        cleanup(import_path)
    except Exception as e:
        logger.warning("올린 파일 정리 실패: %s", e)


def main():
    run_id = os.getenv("MLFLOW_RUN_ID")
    variant = os.getenv("MODEL_VARIANT", "")
    import_path = os.getenv("IMPORT_PATH", "")
    if not run_id or variant not in ("YOLO26", "PP-OCRv6") or not import_path:
        logger.error("MLFLOW_RUN_ID / MODEL_VARIANT / IMPORT_PATH 를 확인하세요.")
        report_status("FAILED", "환경 변수가 올바르지 않습니다")
        sys.exit(1)

    logger.info("--- [START] 모델 가져오기 %s | Job %s ---", variant, JOB_ID)
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    with mlflow.start_run(run_id=run_id):
        try:
            root = download_dataset(import_path, WORK_DIR / "import")
            if job_tags():
                mlflow.set_tags(job_tags())
            mlflow.set_tag("source", "imported")
            prepare = prepare_detection if variant == "YOLO26" else prepare_recognition
            packages, sample = prepare(root)
            mlflow.log_dict(environment_info(packages), "environment.json")

            # 기록한 모델을 다시 불러 한 장 예측해 봅니다 (서빙/평가에서 못 쓰는 파일을 미리 거름)
            model = mlflow.pyfunc.load_model(f"runs:/{run_id}/model")
            out = model.predict(pd.DataFrame({"image": [sample]}))
            logger.info("불러오기 확인: %s", json.dumps(out if isinstance(out, (list, dict)) else str(out),
                                                    ensure_ascii=False, default=str)[:300])

            safe_cleanup(import_path)
            # 완료를 보고하면 백엔드가 컨테이너를 바로 지우므로 run 을 먼저 닫습니다
            mlflow.end_run()
            report_status("FINISHED", "Imported")
            logger.info("--- [DONE] ---")
        except Exception as e:
            logger.error("가져오기 실패:\n%s", traceback.format_exc())
            safe_cleanup(import_path)
            mlflow.end_run(status="FAILED")
            report_status("FAILED", str(e)[:500])
            sys.exit(1)


if __name__ == "__main__":
    main()
