import os
import sys
import traceback
import requests
import mlflow
import json
from ultralytics import YOLO, settings
from utils import download_dataset

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
JOB_ID = os.getenv("JOB_ID")

def report_status(status, message=""):
    if not JOB_ID: return
    try:
        # [수정] v1 경로 반영
        url = f"{BACKEND_URL}/api/v1/jobs/{JOB_ID}/complete"
        resp = requests.post(url, json={"status": status, "message": message}, timeout=10)
        print(f"[Webhook] Status: {status} | HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"[Webhook] Error Detail: {resp.text}")
    except Exception as e:
        print(f"[Webhook] Connection Failed: {e}")

def train_yolo():
    run_id = os.getenv("MLFLOW_RUN_ID")
    raw_path = os.getenv("DATASET_PATH") 
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    job_tags_str = os.getenv("JOB_TAGS", "{}")
    
    try:
        job_tags = json.loads(job_tags_str)
    except Exception:
        job_tags = {}
        
    if not run_id:
        print("MLFLOW_RUN_ID가 설정되지 않았습니다.")
        return
    
    # [수정] YOLOv8이 현재 진행 중인 Run ID를 인식하도록 환경 변수 세팅
    os.environ["MLFLOW_RUN_ID"] = run_id
    # MLflow 자동 로깅을 다시 활성화하여 에포크별 지표(History)를 자동으로 남김
    settings.update({"mlflow": True})

    local_data_path = ""
    try:
        print(f"데이터 다운로드 시도: {raw_path}")
        bucket, prefix = raw_path.split('/', 1)
        local_data_path = download_dataset(bucket, prefix)
    except Exception as e:
        report_status("FAILED", str(e))
        sys.exit(1)

    mlflow.set_tracking_uri(tracking_uri)

    # 서버에서 만든 Run을 이어서 사용
    with mlflow.start_run(run_id=run_id):
        try:
            if job_tags:
                print(f"Loaded Job Tags: {job_tags}")
                mlflow.set_tags(job_tags)
            model = YOLO(os.getenv("MODEL_ARCHITECTURE", "yolov8n.pt"))
            
            # 파라미터 로깅
            epochs = int(os.getenv("EPOCHS", 10))
            batch = int(os.getenv("BATCH", 16))
            mlflow.log_params({"epochs": epochs, "batch": batch})

            # 5. 모델 학습 시작
            # plots=True를 설정해야 시각화 파일들이 생성됨
            results = model.train(
                data=os.path.join(local_data_path, "data.yaml"),
                epochs=epochs,
                batch=batch,
                device=0,
                project='/app/runs',
                name='exp',
                plots=True 
            )

            # 학습 결과 폴더 전체를 'plots'라는 경로로 MLflow에 업로드
            # 여기에 val_batch0_labels.jpg 등이 모두 포함되어 올라감
            if os.path.exists(results.save_dir):
                print(f"Uploading artifacts from {results.save_dir}...")
                mlflow.log_artifacts(results.save_dir, artifact_path="plots")

            best_pt = os.path.join(results.save_dir, "weights", "best.pt")
            if os.path.exists(best_pt):
                mlflow.log_artifact(best_pt, artifact_path="model/weights")
            report_status("FINISHED", "Training completed successfully.")

        except Exception as e:
            traceback.print_exc()
            report_status("FAILED", str(e))
            sys.exit(1)

if __name__ == "__main__":
    train_yolo()