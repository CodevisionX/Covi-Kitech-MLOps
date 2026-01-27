import os
import glob
import torch
import mlflow
import bentoml
import numpy as np

class CnnRunnable(bentoml.Runnable):
    SUPPORTED_RESOURCES = ("cpu", "nvidia.com/gpu")
    SUPPORTS_CPU_MULTI_THREADING = True

    def __init__(self, model_tag):
        bento_model = bentoml.models.get(model_tag)
        model_path = os.path.join(bento_model.path, "mlflow_model")

        print(f"DEBUG: BentoML Model Path: {model_path}")
        print(f"DEBUG: Contents of path: {os.listdir(bento_model.path)}")

        if not os.path.exists(os.path.join(model_path, "MLmodel")):
            found = glob.glob(os.path.join(bento_model.path, "**/MLmodel"), recursive=True)
            if found: model_path = os.path.dirname(found[0])

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"DEBUG: Loading model onto device: {device}")

        # MLflow 모델 로드
        self.model = mlflow.pytorch.load_model(model_path, map_location=device)
        self.model.eval()
        if device.type == 'cuda':
            self.model.cuda()

    @bentoml.Runnable.method(batchable=True)
    def predict(self, input_data):
        # input_data shape: (Batch, Window_size, Input_dim)
        input_tensor = torch.as_tensor(input_data, dtype=torch.float32)
        if torch.cuda.is_available():
            input_tensor = input_tensor.cuda()

        with torch.no_grad():
            outputs = self.model(input_tensor)
            
            # 출력 노드가 1개보다 많으면 분류(Classification), 1개면 회귀(Regression)로 가정
            if outputs.shape[1] > 1:
                _, predicted = torch.max(outputs, 1)
                return predicted.cpu().numpy()
            else:
                return outputs.cpu().numpy() # 회귀 결과값 그대로 반환