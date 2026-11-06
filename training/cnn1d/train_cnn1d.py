"""시계열 1D-CNN 학습 (등록 데이터셋 버전 기준, 플랫폼 작업용 진입점).

흐름: 데이터 다운로드 -> 구조 검사 -> 학습(에폭별 train/val 지표 MLflow 기록)
      -> Validation 기준 체크포인트 선택 -> Validation/Test 평가 -> pyfunc 모델 기록

데이터 구조는 dataset_tools.validate_timeseries 참고:
  {train,val[,test]}/X.npy, y.npy  +  meta.json (선택: problem, class_names)
체크포인트 선택: 분류는 val 정확도 최고(같으면 val loss 낮은 쪽), 회귀는 val loss 최저.
모델 구조는 기존(v1) 1D-CNN 과 같습니다. 각 설정은 같은 이름의 대문자 환경 변수로 바꿀 수 있습니다.
"""
import json
import os
import random
import sys
import traceback
from pathlib import Path

import mlflow
import numpy as np
import torch
import torch.nn as nn
from mlflow.models import ModelSignature
from mlflow.types import ColSpec, Schema
from torch.utils.data import DataLoader, Dataset

from cnn1d_pyfunc import as_batch, build_model
from dataset_tools import read_ts_meta, validate_timeseries
from mlops_common import (
    JOB_ID, WORK_DIR, dataset_manifest, download_dataset, env_float, env_int, environment_info,
    job_tags, logger, report_status, sha256_file, verify_registered_manifest,
)

PACKAGES = ["torch", "numpy", "mlflow"]


class NpyDataset(Dataset):
    """mmap 으로 연 배열에서 배치 단위로만 읽습니다 (큰 데이터도 메모리에 다 올리지 않음)."""

    def __init__(self, X, y, cfg):
        self.X, self.y, self.cfg = X, y, cfg

    def __len__(self):
        return len(self.X)

    def __getitem__(self, i):
        x = torch.from_numpy(as_batch(np.array(self.X[i]), self.cfg)[0])
        if self.cfg["problem"] == "classification":
            return x, torch.tensor(int(np.asarray(self.y[i]).reshape(-1)[0]), dtype=torch.long)
        t = np.array(self.y[i], dtype=np.float32).reshape(-1)  # mmap 은 읽기 전용이라 복사
        return x, torch.from_numpy(t)


def load_split(root: Path, split: str):
    d = root / split
    if not (d / "X.npy").is_file():
        return None
    return np.load(d / "X.npy", mmap_mode="r"), np.load(d / "y.npy", mmap_mode="r")


def run_epoch(model, loader, criterion, device, cfg, optimizer=None):
    """한 에폭을 돌고 지표를 돌려줍니다 (optimizer 가 있으면 학습, 없으면 평가)."""
    train = optimizer is not None
    model.train(train)
    total, n = 0.0, 0
    preds, targets = [], []
    with torch.set_grad_enabled(train):
        for bx, by in loader:
            bx, by = bx.to(device), by.to(device)
            out = model(bx)
            loss = criterion(out, by)
            if train:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
            total += loss.item() * len(bx)
            n += len(bx)
            preds.append(out.argmax(1).cpu().numpy() if cfg["problem"] == "classification"
                         else out.detach().cpu().numpy())
            targets.append(by.cpu().numpy())
    p, t = np.concatenate(preds), np.concatenate(targets)
    m = {"loss": total / max(n, 1)}
    if cfg["problem"] == "classification":
        m["acc"] = float((p == t).mean())
        m["f1"] = macro_f1(t, p, cfg["output_dim"])
    else:
        err = p - t
        m["mae"] = float(np.abs(err).mean())
        m["rmse"] = float(np.sqrt((err ** 2).mean()))
        var = float(((t - t.mean(0)) ** 2).sum())
        m["r2"] = float(1 - (err ** 2).sum() / var) if var > 0 else 0.0
    return m, p, t


def macro_f1(t, p, k):
    f1s = []
    for c in range(k):
        tp = int(((p == c) & (t == c)).sum())
        fp = int(((p == c) & (t != c)).sum())
        fn = int(((p != c) & (t == c)).sum())
        if tp + fp + fn == 0:
            continue  # 정답·예측 모두 없는 클래스는 제외
        f1s.append(2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f1s)) if f1s else 0.0


def better(cur: dict, best: dict, problem: str) -> bool:
    if best is None:
        return True
    if problem == "classification":
        return cur["acc"] > best["acc"] or (cur["acc"] == best["acc"] and cur["loss"] < best["loss"])
    return cur["loss"] < best["loss"]


def confusion(t, p, k):
    cm = np.zeros((k, k), dtype=int)
    for a, b in zip(t, p):
        cm[int(a), int(b)] += 1
    return cm.tolist()


def log_model(weights: Path, cfg_path: Path):
    mlflow.pyfunc.log_model(
        name="model",
        python_model=str(Path(__file__).resolve().parent / "cnn1d_pyfunc.py"),
        artifacts={"weights": str(weights), "config": str(cfg_path)},
        signature=ModelSignature(inputs=Schema([ColSpec("string", "npy")])),
        pip_requirements=["torch", "numpy"],
    )


def main():
    run_id = os.getenv("MLFLOW_RUN_ID")
    if not run_id:
        logger.error("MLFLOW_RUN_ID 가 없습니다.")
        sys.exit(1)
    logger.info("--- [START] 1D-CNN 시계열 학습 | Job %s ---", JOB_ID)
    data_dir, out_dir = WORK_DIR / "data", WORK_DIR / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))

    with mlflow.start_run(run_id=run_id):
        try:
            # 1. 데이터 준비 및 검사 (등록 때와 같은 규칙)
            dataset_path = os.getenv("DATASET_PATH", "")
            download_dataset(dataset_path, data_dir)
            stats, rep = validate_timeseries(data_dir)
            if rep.n_errors:
                raise ValueError("데이터셋 검사 실패:\n" + "\n".join(rep.errors[:20]))
            for w in rep.warnings[:20]:
                logger.warning(w)
            manifest = dataset_manifest(data_dir)
            verify_registered_manifest(manifest)
            meta = read_ts_meta(data_dir)
            cfg = {
                "problem": stats["problem"], "window": stats["window"], "channels": stats["channels"],
                "output_dim": stats["num_classes"] if stats["problem"] == "classification" else stats["outputs"],
                "class_names": meta.get("class_names"),
            }
            logger.info("데이터 검사 통과: %s | %s", stats["counts"], cfg)

            # 2. 설정과 재현 정보 기록
            seed = env_int("SEED", 42)
            random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
            opts = {"epochs": env_int("EPOCHS", 50), "batch": env_int("BATCH", 32),
                    "learning_rate": env_float("LEARNING_RATE", 0.001), "seed": seed,
                    "patience": env_int("PATIENCE", 0), "workers": env_int("WORKERS", 2)}
            if job_tags():
                mlflow.set_tags(job_tags())
            mlflow.set_tags({"task": "timeseries", "model_family": "1D-CNN", "problem": cfg["problem"],
                             "dataset_path": dataset_path, "dataset_sha256": manifest["sha256"]})
            mlflow.log_params({**opts, **{k: v for k, v in cfg.items() if k != "class_names"},
                               "dataset_sha256": manifest["sha256"],
                               "dataset_file_count": manifest["file_count"],
                               **{f"n_{s}_samples": c["samples"] for s, c in stats["counts"].items()}})
            mlflow.log_dict(manifest, "dataset/manifest.json")
            mlflow.log_dict(stats, "dataset/summary.json")
            mlflow.log_dict(environment_info(PACKAGES), "environment.json")

            # 3. 학습
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            g = torch.Generator().manual_seed(seed)
            loaders = {}
            for split in ("train", "val", "test"):
                arrays = load_split(data_dir, split)
                if arrays:
                    loaders[split] = DataLoader(NpyDataset(*arrays, cfg), batch_size=opts["batch"],
                                                shuffle=split == "train", generator=g,
                                                num_workers=opts["workers"], pin_memory=device.type == "cuda")
            model = build_model(cfg).to(device)
            criterion = nn.CrossEntropyLoss() if cfg["problem"] == "classification" else nn.MSELoss()
            optimizer = torch.optim.Adam(model.parameters(), lr=opts["learning_rate"])
            best, best_epoch, ckpt = None, 0, out_dir / "best.pt"
            for epoch in range(1, opts["epochs"] + 1):
                tr, _, _ = run_epoch(model, loaders["train"], criterion, device, cfg, optimizer)
                va, _, _ = run_epoch(model, loaders["val"], criterion, device, cfg)
                mlflow.log_metrics({**{f"train/{k}": v for k, v in tr.items()},
                                    **{f"val/{k}": v for k, v in va.items()}}, step=epoch)
                logger.info("Epoch %d/%d  train %s  val %s", epoch, opts["epochs"],
                            json.dumps({k: round(v, 4) for k, v in tr.items()}),
                            json.dumps({k: round(v, 4) for k, v in va.items()}))
                if better(va, best, cfg["problem"]):
                    best, best_epoch = va, epoch
                    torch.save(model.state_dict(), ckpt)
                elif opts["patience"] and epoch - best_epoch >= opts["patience"]:
                    logger.info("Validation 개선이 %d 에폭 동안 없어 조기 종료합니다.", opts["patience"])
                    break
            mlflow.set_tags({"checkpoint_selection": "best_val_acc" if cfg["problem"] == "classification"
                             else "best_val_loss", "best_epoch": str(best_epoch)})

            # 4. 선택된 체크포인트로 Validation / Test 평가
            model.load_state_dict(torch.load(ckpt, map_location=device))
            final = {}
            for split, prefix in (("val", "best_val"), ("test", "test")):
                if split not in loaders:
                    logger.warning("Test 분할(test/)이 없어 Test 평가를 건너뜁니다.")
                    mlflow.set_tag("test_split", "missing")
                    continue
                m, p, t = run_epoch(model, loaders[split], criterion, device, cfg)
                final.update({f"{prefix}/{k}": v for k, v in m.items()})
                if cfg["problem"] == "classification":
                    mlflow.log_dict({"labels": list(range(cfg["output_dim"])),
                                     "class_names": cfg["class_names"],
                                     "matrix": confusion(t, p, cfg["output_dim"])},
                                    f"evaluation/{split}_confusion_matrix.json")
            mlflow.log_metrics(final)
            logger.info("최종 평가: %s", json.dumps(final, ensure_ascii=False))

            # 5. 모델 기록
            cfg_path = out_dir / "model_config.json"
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
            mlflow.log_param("model_sha256", sha256_file(ckpt))
            log_model(ckpt, cfg_path)

            # 완료를 보고하면 백엔드가 컨테이너를 바로 지우므로 run 을 먼저 닫습니다
            mlflow.end_run()
            report_status("FINISHED", "Training completed successfully.")
            logger.info("--- [DONE] ---")
        except Exception as e:
            logger.error("학습 실패:\n%s", traceback.format_exc())
            mlflow.end_run(status="FAILED")
            report_status("FAILED", str(e))
            sys.exit(1)


if __name__ == "__main__":
    main()
