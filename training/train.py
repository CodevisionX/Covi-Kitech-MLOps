# training/train.py
import os
import mlflow
from ultralytics import YOLO

# 1. MLflow 설정
mlflow.set_tracking_uri("http://mlflow:5000")
experiment_name = "YOLOv8_Manufacturing_Test"
mlflow.set_experiment(experiment_name)

def train_yolo():
    print("🚀 학습 시작...")
    
    model = YOLO('yolov8n.pt') 

    with mlflow.start_run() as run:
        print(f"✅ MLflow Run ID: {run.info.run_id}")
        
        params = {"epochs": 3, "batch": 16, "imgsz": 640}
        mlflow.log_params(params)

        # 3. 학습 실행
        results = model.train(
            data='coco8.yaml',
            epochs=params["epochs"],
            imgsz=params["imgsz"],
            batch=params["batch"],
            project='/app/runs',
            name='train_exp',
            exist_ok=True 
        )

        # 4. 저장 경로 확인
        save_dir = results.save_dir
        best_model_path = os.path.join(save_dir, "weights", "best.pt")
        
        print(f"📂 모델 경로 확인: {best_model_path}")

        if os.path.exists(best_model_path):
            print("📦 모델(.pt)을 MLflow Artifact로 업로드 중...")
            
            # [수정된 부분] log_model 대신 log_artifact 사용!
            # .pt 파일 자체를 'model'이라는 폴더 안에 업로드합니다.
            mlflow.log_artifact(best_model_path, artifact_path="model")
            
            print("✅ 업로드 완료!")
        else:
            print(f"❌ 파일을 찾을 수 없습니다. 경로: {best_model_path}")

if __name__ == "__main__":
    train_yolo()