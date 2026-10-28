"""MLflow pyfunc 래퍼: PP-OCRv6 숫자 인식 모델(내보낸 inference.json/.pdiparams/.yml).

PaddleOCR 패키지 없이 paddle.inference 만으로 실행합니다.
전처리(높이 48 맞춤 리사이즈, [-1, 1] 정규화, 오른쪽 패딩)와 CTC 디코딩은
PaddleOCR tools/infer/predict_rec.py 의 기본 경로와 같습니다.

입력: 'image' 열(base64 로 인코딩한 잘라낸 숫자 이미지)을 가진 DataFrame, 또는 base64 문자열 리스트
출력: 이미지마다 {"text": str, "score": float}
"""
import base64
import math
import os

import mlflow.models
import mlflow.pyfunc


class PPOCRRecognizer(mlflow.pyfunc.PythonModel):
    IMG_C, IMG_H, IMG_W = 3, 48, 320

    def load_context(self, context):
        import paddle.inference as pi
        import yaml

        model_dir = context.artifacts["inference_dir"]
        with open(os.path.join(model_dir, "inference.yml"), encoding="utf-8") as f:
            meta = yaml.safe_load(f)
        self.characters = list(meta["PostProcess"]["character_dict"])

        cfg = pi.Config(os.path.join(model_dir, "inference.json"),
                        os.path.join(model_dir, "inference.pdiparams"))
        try:
            import paddle
            use_gpu = paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0
        except Exception:
            use_gpu = False
        if use_gpu:
            cfg.enable_use_gpu(500, 0)
        else:
            cfg.disable_gpu()
            cfg.disable_mkldnn()
        cfg.disable_glog_info()
        self.predictor = pi.create_predictor(cfg)
        self.input = self.predictor.get_input_handle(self.predictor.get_input_names()[0])
        self.output = self.predictor.get_output_handle(self.predictor.get_output_names()[0])
        self.labels = None  # 첫 추론에서 출력 클래스 수를 보고 확정

    def _preprocess(self, img):
        import cv2
        import numpy as np

        h, w = img.shape[:2]
        img_w = max(self.IMG_W, int(self.IMG_H * w / float(h)))
        resized_w = min(img_w, int(math.ceil(self.IMG_H * w / float(h))))
        x = cv2.resize(img, (resized_w, self.IMG_H)).astype("float32")
        x = (x.transpose((2, 0, 1)) / 255.0 - 0.5) / 0.5
        out = np.zeros((self.IMG_C, self.IMG_H, img_w), dtype="float32")
        out[:, :, :resized_w] = x
        return out[np.newaxis]

    def _decode(self, probs):
        import numpy as np

        if self.labels is None:
            n = probs.shape[-1]
            # 학습 설정 use_space_char=true 이면 공백이 사전 끝에 추가됨 (blank + 사전 + 공백)
            self.labels = ["blank"] + self.characters + ([" "] if n == len(self.characters) + 2 else [])
            if len(self.labels) != n:
                raise ValueError(f"문자 사전 크기({len(self.characters)})와 모델 출력({n})이 맞지 않습니다")
        idx = probs.argmax(axis=-1)
        prob = probs.max(axis=-1)
        chars, scores, prev = [], [], -1
        for i, p in zip(idx, prob):
            if i != 0 and i != prev:
                chars.append(self.labels[i])
                scores.append(float(p))
            prev = i
        return "".join(chars), (float(np.mean(scores)) if scores else 0.0)

    def predict(self, context, model_input, params=None):
        import cv2
        import numpy as np

        items = list(model_input["image"]) if hasattr(model_input, "columns") else list(model_input)
        out = []
        for item in items:
            raw = base64.b64decode(item) if isinstance(item, str) else bytes(item)
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("이미지를 디코딩할 수 없습니다")
            x = self._preprocess(img)
            self.input.reshape(x.shape)
            self.input.copy_from_cpu(x)
            self.predictor.run()
            probs = self.output.copy_to_cpu()[0]
            text, score = self._decode(probs)
            out.append({"text": text, "score": score})
        return out


# MLflow models-from-code: 이 파일 자체를 모델 정의로 기록합니다(pickle 미사용).
mlflow.models.set_model(PPOCRRecognizer())
