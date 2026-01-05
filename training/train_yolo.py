import os
import sys
import logging
import traceback
import requests
import mlflow
import json
import bentoml
from ultralytics import YOLO, settings
from utils import download_dataset
import mlflow.pytorch

# 1. 환경 변수 및 초기 설정
os.environ["GIT_PYTHON_REFRESH"] = "quiet"
os.environ["MLFLOW_PYTHON_IGNORE_GIT_ERROR"] = "true"
os.environ["MLFLOW_TRACKING_GIT_URL"] = "NONE"

# 2. 로깅 설정
LOG_DIR = "/app/runs/logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

JOB_ID = os.getenv("JOB_ID", "unknown")
LOG_FILE_PATH = os.path.join(LOG_DIR, f"job_{JOB_ID}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# YOLO 자동 MLflow 로깅 비활성화 (충돌 방지)
settings.update({"mlflow": False})

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# --- 커스텀 콜백 함수 정의 ---
def on_fit_epoch_end(trainer):
    """
    매 Epoch(학습+검증)가 끝날 때마다 호출되어 MLflow에 지표를 수동으로 기록합니다.
    (MLflow 이름 규칙 위반 방지를 위해 특수문자 치환 로직 추가)
    """
    metrics = {}
    
    # 1. 학습 Loss 기록
    if hasattr(trainer, 'loss_items') and trainer.loss_items is not None:
        for i, name in enumerate(trainer.loss_names):
            # name에 혹시 모를 괄호가 있다면 제거
            clean_name = name.replace("(", "_").replace(")", "")
            metrics[f"train/{clean_name}"] = float(trainer.loss_items[i])

    # 2. 검증 지표 기록 (여기가 에러 원인)
    # trainer.metrics 키 예시: 'metrics/precision(B)', 'metrics/mAP50(B)' 등
    if hasattr(trainer, 'metrics') and trainer.metrics:
        for k, v in trainer.metrics.items():
            # [핵심 수정] 괄호 '('는 '_'로, ')'는 제거하여 MLflow 호환 이름으로 변경
            # 예: metrics/precision(B) -> metrics/precision_B
            clean_key = k.replace("(", "_").replace(")", "")
            metrics[clean_key] = float(v)

    # 3. Learning Rate 기록
    if hasattr(trainer, 'optimizer') and trainer.optimizer:
        metrics['lr/pg0'] = float(trainer.optimizer.param_groups[0]['lr'])

    # 4. MLflow에 전송
    if metrics:
        try:
            mlflow.log_metrics(metrics, step=trainer.epoch + 1)
        except Exception as e:
            # 혹시라도 또 다른 이름 규칙 위반이 있을 경우 로그만 남기고 학습은 계속 진행되도록 함
            print(f"[Warning] MLflow log_metrics failed: {e}")


def report_status(status, message=""):
    if not JOB_ID or JOB_ID == "unknown": return
    try:
        url = f"{BACKEND_URL}/api/v1/jobs/{JOB_ID}/complete"
        resp = requests.post(url, json={"status": status, "message": message}, timeout=10)
        logger.info(f"[Webhook] Status: {status} | HTTP {resp.status_code}")
    except Exception as e:
        logger.error(f"[Webhook] Connection Failed: {e}")

def train_yolo():
    logger.info(f"--- [START] Job ID: {JOB_ID} ---")
    
    run_id = os.getenv("MLFLOW_RUN_ID")
    raw_path = os.getenv("DATASET_PATH") 
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    job_tags_str = os.getenv("JOB_TAGS", "{}")
    
    try:
        job_tags = json.loads(job_tags_str)
    except Exception:
        job_tags = {}
        
    if not run_id:
        logger.error("MLFLOW_RUN_ID가 설정되지 않았습니다.")
        return
    
    os.environ["MLFLOW_RUN_ID"] = run_id
    local_data_path = ""

    try:
        logger.info(f"데이터 다운로드 시도: {raw_path}")
        bucket, prefix = raw_path.split('/', 1)
        local_data_path = download_dataset(bucket, prefix)
    except Exception as e:
        logger.error(f"데이터 다운로드 실패: {e}")
        report_status("FAILED", str(e))
        sys.exit(1)

    mlflow.set_tracking_uri(tracking_uri)

    with mlflow.start_run(run_id=run_id):
        try:
            if job_tags:
                mlflow.set_tags(job_tags)

            model = YOLO(os.getenv("MODEL_ARCHITECTURE", "yolov8n.pt"))
            
            # 파라미터 로깅
            epochs = int(os.getenv("EPOCHS", 10))
            batch = int(os.getenv("BATCH", 16))
            mlflow.log_params({"epochs": epochs, "batch": batch})

            # 기존 YOLO 자동 MLflow 콜백 제거 (충돌 방지)
            from ultralytics.utils.callbacks.mlflow import callbacks as mlflow_cb
            for event, func_list in model.callbacks.items():
                if mlflow_cb.get('on_pretrain_routine_start') in func_list:
                    model.callbacks[event] = [f for f in func_list if f not in mlflow_cb.values()]
            
            # --- 커스텀 콜백 등록 ---
            # 'on_fit_epoch_end'는 검증(Validation)까지 마친 후 호출되므로 mAP와 Loss를 모두 가집니다.
            model.add_callback("on_fit_epoch_end", on_fit_epoch_end)
            logger.info("Custom MLflow Callback registered successfully.")
            # ---------------------------

            # 5. 모델 학습 시작
            results = model.train(
                data=os.path.join(local_data_path, "data.yaml"),
                epochs=epochs,
                batch=batch,
                device=0,
                project='/app/runs',
                name='exp',
                plots=True,
            )
            
            logger.info("--- [DEBUG] 학습 프로세스 종료, 모델 아티팩트 저장 시작 ---")

            try:
                best_pt = os.path.join(results.save_dir, "weights", "best.pt")
                if os.path.exists(best_pt):
                    logger.info("Logging YOLO model to MLflow...")
                    final_model = YOLO(best_pt)
                    
                    mlflow.pytorch.log_model(
                        pytorch_model=final_model.model,
                        artifact_path="model",
                        registered_model_name=os.getenv("MODEL_NAME", "YOLOv8_Defect"),
                        pip_requirements=["ultralytics", "torch", "torchvision"]
                    )
                    
                    logger.info("Saving to BentoML...")
                    bentoml.pytorch.save_model(
                        os.getenv("BENTO_MODEL_NAME", "yolov8_defect_model"),
                        final_model.model,
                        signatures={"predict": {"batchable": True}},
                        metadata={
                            "task": "detect",
                            "epochs": epochs,
                            "job_id": JOB_ID,
                            "mlflow_run_id": run_id
                        }
                    )
                else:
                    logger.warning(f"best.pt 파일을 찾을 수 없습니다: {best_pt}")
            except Exception as e:
                logger.error(f"모델 등록 중 에러 발생: {e}")
                logger.error(traceback.format_exc())

            if os.path.exists(results.save_dir):
                mlflow.log_artifacts(results.save_dir, artifact_path="plots")

            report_status("FINISHED", "Training completed successfully.")

        except Exception as e:
            logger.error("학습 도중 에러 발생")
            logger.error(traceback.format_exc())
            report_status("FAILED", str(e))
            sys.exit(1)

if __name__ == "__main__":
    train_yolo()