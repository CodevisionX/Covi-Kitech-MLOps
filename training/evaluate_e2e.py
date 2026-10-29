"""E2E 평가: 검출 모델과 인식 모델을 운영과 같은 순서로 이어 붙여 슬롯 단위로 채점합니다.

패널 이미지 -> YOLO 숫자 묶음 검출 -> 정확히 6개면 2x3 슬롯 정렬 -> Crop -> PP-OCR 인식 -> 정답 비교

검출과 인식은 학습 환경이 달라(torch / paddle) 같은 MLflow run 을 이어 쓰는 두 단계로 실행합니다.
  STAGE=detect     (YOLO26 학습 이미지)  검출, 슬롯 정렬, Crop -> run 아티팩트 stage1/
  STAGE=recognize  (PP-OCR 학습 이미지)  stage1/ 의 Crop 인식, 채점 -> 지표, predictions.csv

환경 변수
  EVALUATION_ID, MLFLOW_RUN_ID, BACKEND_URL
  DATASET_PATH, DATASET_MANIFEST_SHA256      E2E 데이터셋(등록된 버전)
  DETECTION_RUN_ID, RECOGNITION_RUN_ID      평가할 모델(학습 run)
  CONF, IOU, IMGSZ, MAX_DET, PADDING        검출 설정 (기본값은 고객 운영 코드와 같음)
"""
import base64
import csv
import io
import json
import os
import sys
import traceback
import zipfile
from collections import defaultdict
from pathlib import Path

import mlflow
import requests

from dataset_tools import E2E_SLOTS, crop_box, e2e_panels, edit_distance, load_roi_config, read_e2e_labels, sort_boxes_2x3
from mlops_common import (
    BACKEND_URL, WORK_DIR, dataset_manifest, download_dataset, env_float, env_int, environment_info,
    logger, sanitize_metric_name, verify_registered_manifest,
)

EVALUATION_ID = os.getenv("EVALUATION_ID", "")
STAGE = os.getenv("STAGE", "")
RUN_ID = os.getenv("MLFLOW_RUN_ID")
DATA_DIR = WORK_DIR / "data"
STAGE1_DIR = WORK_DIR / "stage1"


def report(status, **payload):
    try:
        r = requests.post(f"{BACKEND_URL}/api/v1/evaluations/{EVALUATION_ID}/report",
                          json={"stage": STAGE, "status": status, **payload}, timeout=30)
        logger.info("[Webhook] %s %s | HTTP %s", STAGE, status, r.status_code)
    except Exception as e:
        logger.error("[Webhook] 연결 실패: %s", e)


def detection_options():
    # 고객 운영 코드(model_detection.py)의 기본값: conf 0.25, iou 0.3, imgsz 640, max_det 20, padding 0, NMS 사용
    return {
        "conf": env_float("CONF", 0.25),
        "iou": env_float("IOU", 0.3),
        "imgsz": env_int("IMGSZ", 640),
        "max_det": env_int("MAX_DET", 20),
        "padding": env_int("PADDING", 0),
    }


def model_files(run_id: str, dest: Path) -> Path:
    """학습 run 에 기록된 모델(pyfunc)의 아티팩트를 받습니다."""
    return Path(mlflow.artifacts.download_artifacts(artifact_uri=f"runs:/{run_id}/model", dst_path=str(dest)))


# ---------------------------------------------------------------- 1단계: 검출
def stage_detect():
    import cv2
    from ultralytics import YOLO

    opts = detection_options()
    root = download_dataset(os.environ["DATASET_PATH"], DATA_DIR)
    manifest = dataset_manifest(root)
    verify_registered_manifest(manifest)
    roi = load_roi_config(root)
    labels, rep = read_e2e_labels(root)
    if rep.n_errors:
        raise ValueError("labels.txt 오류: " + "; ".join(rep.errors[:5]))

    det_dir = model_files(os.environ["DETECTION_RUN_ID"], WORK_DIR / "det_model")
    weights = det_dir / "artifacts" / "best.pt"
    model = YOLO(str(weights))

    # 평가 단위 패널 목록 [(이미지, 패널 이름)]
    panel_label_of = {img: p for img, p in labels}  # 패널 모드에서 이미지 -> 패널 이름
    if roi:
        panels = e2e_panels(root, roi)
    else:
        panels = [(img, panel_label_of.get(img, Path(img).stem)) for img in e2e_panels(root)]
    logger.info("평가 패널 %d개 (%s 모드), 정답 슬롯 %d개", len(panels), "프레임" if roi else "패널",
                sum(len(v) for v in labels.values()))

    frames = {}

    def panel_image(img, name):
        if img not in frames:
            frames.clear()  # 프레임 하나씩만 메모리에 둠 (패널 목록은 이미지 순서로 정렬됨)
            frames[img] = cv2.imread(str(root / img), cv2.IMREAD_COLOR)
            if frames[img] is None:
                raise ValueError(f"이미지를 읽을 수 없습니다: {img}")
        frame = frames[img]
        if not roi:
            return frame
        x1, y1, x2, y2 = roi["panels"][name]
        return frame[y1:y2, x1:x2].copy()

    STAGE1_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    batch = 16
    with zipfile.ZipFile(STAGE1_DIR / "crops.zip", "w", zipfile.ZIP_STORED) as zf:
        for start in range(0, len(panels), batch):
            chunk = panels[start:start + batch]
            images = [panel_image(img, name) for img, name in chunk]
            results = model.predict(images, imgsz=opts["imgsz"], conf=opts["conf"], iou=opts["iou"],
                                    max_det=opts["max_det"], end2end=False, save=False, verbose=False)
            for (img, name), image, r in zip(chunk, images, results):
                boxes = []
                if r.boxes is not None and len(r.boxes):
                    for b, c, k in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(),
                                       r.boxes.cls.cpu().numpy()):
                        boxes.append([float(b[0]), float(b[1]), float(b[2]), float(b[3]), float(c), int(k)])
                rec = {"image": img, "panel": name, "n_boxes": len(boxes), "boxes": boxes, "slots": []}
                if len(boxes) == E2E_SLOTS:
                    for slot, box in enumerate(sort_boxes_2x3(boxes), 1):
                        crop, xyxy = crop_box(image, box, opts["padding"])
                        entry = {"slot": slot, "bbox": list(xyxy), "det_conf": box[4], "crop": None}
                        if crop is not None:
                            ok, buf = cv2.imencode(".png", crop)
                            entry["crop"] = f"{len(records):06d}_{slot}.png"
                            zf.writestr(entry["crop"], buf.tobytes())
                        rec["slots"].append(entry)
                records.append(rec)
            logger.info("  검출 %d/%d", min(start + batch, len(panels)), len(panels))

    ok6 = sum(r["n_boxes"] == E2E_SLOTS for r in records)
    logger.info("6개 검출 패널: %d/%d", ok6, len(records))
    doc = {"options": opts, "mode": "frame" if roi else "panel", "dataset_sha256": manifest["sha256"],
           "labels": [[img, panel, slot, text] for (img, panel), slots in labels.items()
                      for slot, text in sorted(slots.items())],
           "panels": records}
    (STAGE1_DIR / "detections.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    with mlflow.start_run(run_id=RUN_ID):
        mlflow.log_params({f"det_{k}": v for k, v in opts.items()})
        mlflow.log_params({"detection_run_id": os.environ["DETECTION_RUN_ID"],
                           "recognition_run_id": os.environ["RECOGNITION_RUN_ID"],
                           "dataset_sha256": manifest["sha256"], "mode": doc["mode"]})
        mlflow.log_dict(environment_info(["ultralytics", "torch", "opencv-python", "mlflow"]),
                        "stage1/environment.json")
        mlflow.log_artifacts(str(STAGE1_DIR), "stage1")
    report("DONE", message=f"6개 검출 패널 {ok6}/{len(records)}")


# ---------------------------------------------------------------- 2단계: 인식 + 채점
def stage_recognize():
    import pandas as pd

    with mlflow.start_run(run_id=RUN_ID):
        src = Path(mlflow.artifacts.download_artifacts(run_id=RUN_ID, artifact_path="stage1",
                                                       dst_path=str(WORK_DIR)))
    doc = json.loads((src / "detections.json").read_text(encoding="utf-8"))
    rec_model = mlflow.pyfunc.load_model(f"runs:/{os.environ['RECOGNITION_RUN_ID']}/model")

    # Crop 인식
    crops = [(i, s) for i, p in enumerate(doc["panels"]) for s in p["slots"] if s["crop"]]
    preds = {}
    with zipfile.ZipFile(src / "crops.zip") as zf:
        batch = 64
        for start in range(0, len(crops), batch):
            chunk = crops[start:start + batch]
            images = pd.DataFrame({"image": [base64.b64encode(zf.read(s["crop"])).decode() for _, s in chunk]})
            for (i, s), out in zip(chunk, rec_model.predict(images)):
                preds[(i, s["slot"])] = out
            logger.info("  인식 %d/%d", min(start + batch, len(crops)), len(crops))

    # 채점
    gt = defaultdict(dict)
    for img, panel, slot, text in doc["labels"]:
        gt[(img, panel)][int(slot)] = text

    rows = []
    slot_hits, slot_total = defaultdict(int), defaultdict(int)
    panel_hits, panel_total = defaultdict(int), defaultdict(int)
    image_ok = defaultdict(lambda: True)
    labeled_panels = all_correct_panels = 0
    ned_sum = 0.0
    det_slots = det_correct = 0
    for i, p in enumerate(doc["panels"]):
        truth = gt.get((p["image"], p["panel"]), {})
        detected = p["n_boxes"] == E2E_SLOTS
        by_slot = {s["slot"]: s for s in p["slots"]}
        panel_correct = True
        for slot in range(1, E2E_SLOTS + 1):
            s = by_slot.get(slot)
            out = preds.get((i, slot)) if s else None
            pred = out["text"] if out else ""
            text = truth.get(slot)
            correct = text is not None and detected and out is not None and pred == text
            if text is not None:
                slot_total[slot] += 1
                panel_total[p["panel"]] += 1
                slot_hits[slot] += correct
                panel_hits[p["panel"]] += correct
                ned_sum += edit_distance(pred, text) / max(len(pred), len(text), 1)
                if detected:
                    det_slots += 1
                    det_correct += correct
                if not correct:
                    panel_correct = False
                    image_ok[p["image"]] = False
            if text is not None or s is not None:
                rows.append({
                    "image": p["image"], "panel": p["panel"], "slot": slot,
                    "panel_boxes": p["n_boxes"],
                    "gt": "" if text is None else text, "pred": pred,
                    "rec_score": round(out["score"], 4) if out else "",
                    "det_conf": round(s["det_conf"], 4) if s else "",
                    "bbox": " ".join(map(str, s["bbox"])) if s else "",
                    "result": ("unlabeled" if text is None else "correct" if correct
                               else "panel_not_6" if not detected else "wrong"),
                })
        if truth:
            labeled_panels += 1
            all_correct_panels += panel_correct

    n_slots = sum(slot_total.values())
    n_panels = len(doc["panels"])
    labeled_images = {img for img, _ in gt}
    metrics = {
        "e2e/slot_accuracy": sum(slot_hits.values()) / n_slots if n_slots else 0.0,
        "e2e/norm_edit_dis": 1 - ned_sum / n_slots if n_slots else 0.0,
        "e2e/panel_detect6_rate": sum(p["n_boxes"] == E2E_SLOTS for p in doc["panels"]) / n_panels if n_panels else 0.0,
        "e2e/slot_accuracy_on_detected": det_correct / det_slots if det_slots else 0.0,
        "e2e/panel_all_correct_rate": all_correct_panels / labeled_panels if labeled_panels else 0.0,
        "e2e/image_all_correct_rate": (sum(image_ok[i] for i in labeled_images) / len(labeled_images)
                                       if labeled_images else 0.0),
        "e2e/labeled_slots": n_slots,
        "e2e/panels": n_panels,
    }
    for slot in range(1, E2E_SLOTS + 1):
        if slot_total[slot]:
            metrics[f"e2e/slot{slot}_accuracy"] = slot_hits[slot] / slot_total[slot]
    for name in panel_total:
        metrics[sanitize_metric_name(f"e2e/panel/{name}_accuracy")] = panel_hits[name] / panel_total[name]
    per_panel = {name: {"correct": panel_hits[name], "total": panel_total[name],
                        "accuracy": panel_hits[name] / panel_total[name]}
                 for name in sorted(panel_total)}
    per_slot = {str(s): {"correct": slot_hits[s], "total": slot_total[s],
                         "accuracy": slot_hits[s] / slot_total[s] if slot_total[s] else None}
                for s in range(1, E2E_SLOTS + 1)}

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]) if rows else ["image"])
    writer.writeheader()
    writer.writerows(rows)
    errors = [r for r in rows if r["result"] in ("wrong", "panel_not_6")]

    with mlflow.start_run(run_id=RUN_ID):
        mlflow.log_metrics(metrics)
        mlflow.log_text("﻿" + buf.getvalue(), "e2e/predictions.csv")  # 엑셀에서 한글이 깨지지 않도록 BOM
        mlflow.log_dict({"metrics": metrics, "per_slot": per_slot, "per_panel": per_panel,
                         "options": doc["options"], "errors": errors[:500]}, "e2e/summary.json")
        mlflow.log_dict(environment_info(["paddlepaddle-gpu", "paddlepaddle", "opencv-python", "mlflow"]),
                        "e2e/environment.json")
    logger.info("슬롯 정확도 %.4f (%d/%d), 6개 검출 패널 비율 %.4f",
                metrics["e2e/slot_accuracy"], sum(slot_hits.values()), n_slots, metrics["e2e/panel_detect6_rate"])
    report("DONE", metrics=metrics, summary={"per_slot": per_slot, "per_panel": per_panel,
                                             "error_count": len(errors)})


def main():
    logger.info("--- [START] E2E 평가 %s | 단계 %s ---", EVALUATION_ID, STAGE)
    try:
        if STAGE == "detect":
            stage_detect()
        elif STAGE == "recognize":
            stage_recognize()
        else:
            raise ValueError(f"알 수 없는 단계: {STAGE!r}")
    except Exception as e:
        logger.error("E2E 평가 실패:\n%s", traceback.format_exc())
        report("FAILED", message=str(e)[:500])
        sys.exit(1)
    logger.info("--- [DONE] %s ---", STAGE)


if __name__ == "__main__":
    main()
