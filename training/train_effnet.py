import os
import torch
import mlflow
import torchvision
from utils import download_dataset

def train_effnet():
    # GPU 체크
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"학습 장치: {device}")

    # 데이터 다운로드
    raw_path = os.getenv("DATASET_PATH")
    bucket, prefix = raw_path.split('/', 1)
    local_data_path = download_dataset(bucket, prefix)

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI"))

    with mlflow.start_run(run_id=os.getenv("MLFLOW_RUN_ID")):
        # 모델 생성 및 GPU 이동
        model = torchvision.models.efficientnet_b0(pretrained=True)
        model.to(device) # 모델을 GPU로!

        # (가상 학습 루프)
        epochs = int(os.getenv("EPOCHS", 5))
        for epoch in range(epochs):
            # 실제 학습 시 data.to(device) 과정이 필요함
            loss = 0.5 / (epoch + 1)
            mlflow.log_metric("loss", loss, step=epoch)
            print(f"Epoch {epoch}: loss={loss}")

        torch.save(model.state_dict(), "best.pth")
        mlflow.log_artifact("best.pth", artifact_path="model")

if __name__ == "__main__":
    train_effnet()