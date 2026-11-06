"""MLflow pyfunc 래퍼: 시계열 1D-CNN (분류/회귀).

입력: 'npy' 열(base64 로 인코딩한 .npy)을 가진 DataFrame, 또는 base64 문자열 리스트.
      각 .npy 는 샘플 1개 (윈도[, 채널]) 또는 여러 개 (샘플, 윈도[, 채널]).
출력: 입력마다
      분류 {"labels": [정수, ...], "probs": [[클래스별 확률], ...], "names": [라벨 이름, ...](있으면)}
      회귀 {"values": [[출력값, ...], ...]}
"""
import base64
import io
import json

import mlflow.models
import mlflow.pyfunc
import torch
import torch.nn as nn


class Standard1DCNN(nn.Module):
    """기존(v1) 1D-CNN 과 같은 구조: 윈도 축을 입력 채널로 씁니다."""

    def __init__(self, input_dim, window_size, output_dim):
        super().__init__()
        self.conv_layer = nn.Sequential(
            nn.Conv1d(in_channels=window_size, out_channels=64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=2) if input_dim > 1 else nn.Identity(),
            nn.Conv1d(in_channels=64, out_channels=128, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.fc_layer = nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, output_dim))

    def forward(self, x):
        x = self.conv_layer(x)
        return self.fc_layer(x.view(x.size(0), -1))


def build_model(cfg: dict) -> Standard1DCNN:
    return Standard1DCNN(cfg["channels"], cfg["window"], cfg["output_dim"])


def as_batch(arr, cfg: dict):
    """(윈도[, 채널]) 또는 (샘플, 윈도[, 채널]) 를 (샘플, 윈도, 채널) float32 로 맞춥니다."""
    import numpy as np

    a = np.asarray(arr, dtype=np.float32)
    w, c = cfg["window"], cfg["channels"]
    if a.ndim == 1 or (a.ndim == 2 and a.shape == (w, c)):
        a = a[None]
    if a.ndim == 2:
        a = a[..., None]
    if a.ndim != 3 or a.shape[1:] != (w, c):
        raise ValueError(f"입력 모양이 맞지 않습니다: {a.shape} (필요: (샘플, {w}, {c}))")
    return a


class Cnn1dPredictor(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        with open(context.artifacts["config"], encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = build_model(self.cfg).to(self.device)
        self.model.load_state_dict(torch.load(context.artifacts["weights"], map_location=self.device))
        self.model.eval()

    def predict(self, context, model_input, params=None):
        import numpy as np

        items = list(model_input["npy"]) if hasattr(model_input, "columns") else list(model_input)
        out = []
        for item in items:
            raw = base64.b64decode(item) if isinstance(item, str) else bytes(item)
            batch = as_batch(np.load(io.BytesIO(raw), allow_pickle=False), self.cfg)
            with torch.no_grad():
                y = self.model(torch.from_numpy(batch).to(self.device)).cpu()
            if self.cfg["problem"] == "classification":
                probs = torch.softmax(y, dim=1).double().numpy()
                labels = probs.argmax(axis=1).tolist()
                res = {"labels": labels, "probs": probs.round(6).tolist()}
                names = self.cfg.get("class_names")
                if names:
                    res["names"] = [names[i] if i < len(names) else str(i) for i in labels]
            else:
                res = {"values": y.double().numpy().round(6).tolist()}
            out.append(res)
        return out


# MLflow models-from-code: 이 파일 자체를 모델 정의로 기록합니다(pickle 미사용).
mlflow.models.set_model(Cnn1dPredictor())
