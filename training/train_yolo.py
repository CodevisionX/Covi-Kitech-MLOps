import os
import mlflow
from ultralytics import YOLO
from utils import download_dataset # 위 유틸리티 임포트

def train_yolo():
    # 1. 환경변수 및 경로 설정
    run_id = os.getenv("MLFLOW_RUN_ID")
    raw_path = os.getenv("DATASET_PATH") # 예: "mlops-bucket/pcb-dataset"
    bucket, prefix = raw_path.split('/', 1)
    
    # 2. 데이터 다운로드
    local_data_path = download_dataset(bucket, prefix)

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI"))

    with mlflow.start_run(run_id=run_id):
        # 3. 모델 로드 및 GPU 학습 (device=0)
        model = YOLO(os.getenv("MODEL_VARIANT", "yolov8n.pt"))
        
        results = model.train(
            data=os.path.join(local_data_path, "data.yaml"), # 다운로드된 경로의 yaml 사용
            epochs=int(os.getenv("EPOCHS", 10)),
            batch=int(os.getenv("BATCH", 16)),
            device=0, # ✅ GPU 사용 강제
            project='/app/runs',
            name='exp'
        )

        # Artifact 업로드 (기존과 동일)
        best_pt = os.path.join(results.save_dir, "weights", "best.pt")
        mlflow.log_artifact(best_pt, artifact_path="model")

if __name__ == "__main__":
    train_yolo()