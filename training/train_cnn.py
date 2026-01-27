import os
import sys
import logging
import json
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, f1_score, accuracy_score
import mlflow
import mlflow.pytorch
import bentoml
from utils import download_dataset
import requests
import traceback

# 1. 환경 설정
os.environ["GIT_PYTHON_REFRESH"] = "quiet"
os.environ["MLFLOW_PYTHON_IGNORE_GIT_ERROR"] = "true"
JOB_ID = os.getenv("JOB_ID", "unknown")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# 2. 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# --- 3. 모델 정의 ---
class Standard1DCNN(nn.Module):
    def __init__(self, input_dim, window_size, output_dim):
        super(Standard1DCNN, self).__init__()
        self.conv_layer = nn.Sequential(
            nn.Conv1d(in_channels=window_size, out_channels=64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=2) if input_dim > 1 else nn.Identity(),
            nn.Conv1d(in_channels=64, out_channels=128, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1)
        )
        self.fc_layer = nn.Sequential(
            nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, output_dim)
        )

    def forward(self, x):
        x = self.conv_layer(x)
        x = x.view(x.size(0), -1)
        return self.fc_layer(x)

# --- 4. 시각화 및 MLflow 기록 함수 ---
def log_analysis_results(history, y_true, y_pred, X_samples, is_classification):
    plot_dir = "/app/runs/plots"
    os.makedirs(plot_dir, exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5))
    ax2.plot(history['train_loss'], label='Loss', color='red')
    ax2.set_title('Training Loss')
    ax2.legend()

    if is_classification:
        ax1.plot(history['train_acc'], label='Accuracy', color='blue')
        ax1.set_title('Training Accuracy')
        f1 = f1_score(y_true, y_pred, average='macro')
        mlflow.log_metric("final_f1_score", f1)
    else:
        ax1.plot(history['train_loss'], label='MSE', color='green')
        ax1.set_title('Training MSE')

    ax1.legend()
    plt.savefig(f"{plot_dir}/learning_curves.png")
    mlflow.log_artifact(f"{plot_dir}/learning_curves.png")

    if is_classification:
        plt.figure(figsize=(10, 8))
        cm = confusion_matrix(y_true, y_pred)
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues')
        plt.title('Confusion Matrix')
        plt.savefig(f"{plot_dir}/confusion_matrix.png")
        mlflow.log_artifact(f"{plot_dir}/confusion_matrix.png")

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for i, ax in enumerate(axes.flat):
        if i < len(X_samples):
            ax.plot(X_samples[i][:, 0], color='gray', alpha=0.8)
            is_correct = (y_true[i] == y_pred[i]) if is_classification else True
            title_color = 'green' if is_correct else 'red'
            ax.set_title(f"Sample {i} | True: {y_true[i]} | Pred: {y_pred[i]}",
                         color=title_color, fontsize=10, fontweight='bold')
            ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(f"{plot_dir}/sensor_samples.png")
    mlflow.log_artifact(f"{plot_dir}/sensor_samples.png")
    plt.close('all')

def report_status(status, message=""):
    try:
        requests.post(f"{BACKEND_URL}/api/v1/jobs/{JOB_ID}/complete",
                      json={"status": status, "message": message}, timeout=10)
    except: pass

class MmapDataset(Dataset):
    """
    mmap_mode로 로드된 numpy 배열을 직접 참조하여 
    배치 단위로만 메모리에 로드하는 커스텀 데이터셋입니다.
    """
    def __init__(self, X_mmap, y_mmap, is_classification):
        self.X = X_mmap
        self.y = y_mmap
        self.is_classification = is_classification

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        # 해당 인덱스의 데이터만 numpy에서 읽어와 텐서로 변환합니다.
        # np.array()로 감싸주어야 mmap 참조가 실제 데이터로 실체화됩니다.
        bx = torch.from_numpy(np.array(self.X[idx])).float()
        
        if self.is_classification:
            # 분류 문제일 경우 Label을 LongTensor로 변환 (TEP 등)
            by = torch.tensor(self.y[idx], dtype=torch.long).ravel()[0]
        else:
            # 회귀 문제일 경우 Label을 FloatTensor로 변환 (Gas Turbine 등)
            by = torch.from_numpy(np.array(self.y[idx])).float()
            
        return bx, by
    
def train_cnn():
    run_id = os.getenv("MLFLOW_RUN_ID")
    raw_path = os.getenv("DATASET_PATH")
    epochs = int(os.getenv("EPOCHS", 50))
   
    try:
        bucket, prefix = raw_path.split('/', 1)
        local_data_path = download_dataset(bucket, prefix)
        X = np.load(f"{local_data_path}/X.npy", mmap_mode='r')
        y = np.load(f"{local_data_path}/y.npy", mmap_mode='r')
        
        window_size, input_dim = X.shape[1], X.shape[2]
        logger.info(f"Dataset loaded with mmap. Shape: {X.shape}")
    except Exception as e:
        report_status("FAILED", str(e)); sys.exit(1)

    is_classification = "tep" in raw_path.lower()
    output_dim = int(np.max(y) + 1) if is_classification else y.shape[1]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = Standard1DCNN(input_dim, window_size, output_dim).to(device)
    criterion = nn.CrossEntropyLoss() if is_classification else nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=float(os.getenv("LEARNING_RATE", 0.001)))

    train_dataset = MmapDataset(X, y, is_classification)
    loader = DataLoader(
        train_dataset, 
        batch_size=int(os.getenv("BATCH", 32)), 
        shuffle=False,
        num_workers=2,      # 데이터 로딩 병렬화 (선택 사항)
        pin_memory=True if torch.cuda.is_available() else False
    )

    history = {'train_loss': [], 'train_acc': []}
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))

    with mlflow.start_run(run_id=run_id) as run:
        try:
            learning_rate = float(os.getenv("LEARNING_RATE", 0.001))
            batch_size = int(os.getenv("BATCH", 32))
            
            mlflow.log_params({
                "epochs": epochs,
                "batch_size": batch_size,
                "learning_rate": learning_rate,
                "window_size": window_size,
                "input_dim": input_dim,
                "is_classification": is_classification,
                "job_id": JOB_ID
            })
            logger.info(f"Parameters logged to MLflow: epochs={epochs}, batch={batch_size}, lr={learning_rate}")
            
            for epoch in range(epochs):
                model.train()
                total_loss, correct, total = 0, 0, 0
                for bx, by in loader:
                    bx, by = bx.to(device), by.to(device)
                    optimizer.zero_grad(); outputs = model(bx); loss = criterion(outputs, by)
                    loss.backward(); optimizer.step(); total_loss += loss.item()
                    if is_classification:
                        _, pred = torch.max(outputs, 1); total += by.size(0); correct += (pred == by).sum().item()

                history['train_loss'].append(total_loss/len(loader))
                history['train_acc'].append(correct/total if is_classification else 0)
                mlflow.log_metric("train_loss", history['train_loss'][-1], step=epoch)

            # 최종 평가 및 시각화
            model.eval(); all_preds, all_labels = [], []
            with torch.no_grad():
                for bx, by in loader:
                    out = model(bx.to(device))
                    if is_classification:
                        _, p = torch.max(out, 1); all_preds.extend(p.cpu().numpy()); all_labels.extend(by.numpy())
                    else:
                        all_preds.extend(out.cpu().numpy()); all_labels.extend(by.numpy())

            log_analysis_results(history, all_labels, all_preds, X[:4], is_classification)

            mlflow.set_tag("model_type", "cnn")
            mlflow.set_tag("type", "classification" if is_classification else "regression")
            
            # 1. MLflow 모델 로깅
            cnn_metadata = {
                "model_type": "cnn",
                "input_dim": input_dim,
                "window_size": window_size,
                "job_id": JOB_ID,
                "mlflow_run_id": run_id,
                "type": "classification" if is_classification else "regression"
            }

    
            logger.info("Logging CNN model to MLflow...")
            mlflow.pytorch.log_model(
                model, 
                "model",
                metadata=cnn_metadata
            )

            # 2. BentoML 모델 저장 (YOLO 스타일 적용)
            try:
                logger.info("Saving CNN model to BentoML...")
                bentoml.pytorch.save_model(
                    os.getenv("BENTO_MODEL_NAME", "standard_1dcnn_model"),
                    model,
                    signatures={"forward": {"batchable": True}},
                    metadata=cnn_metadata
                )
                logger.info("BentoML model saving successful.")
            except Exception as be:
                logger.error(f"BentoML saving failed: {be}")

            mlflow.set_tag("job_id", JOB_ID)
            logger.info("Closing MLflow run explicitly...")
            mlflow.end_run(status='FINISHED')

            import time
            time.sleep(1)

            report_status("FINISHED", "Success")

        except Exception as e:
            logger.error(f"Error occurred: {e}")
            report_status("FAILED", str(e))
            mlflow.end_run(status='FAILED')
            raise e

if __name__ == "__main__":
    train_cnn()