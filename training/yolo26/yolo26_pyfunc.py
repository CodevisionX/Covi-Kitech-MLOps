"""MLflow pyfunc 래퍼: YOLO26 숫자 그룹 검출 모델.

입력: 'image' 열(base64 로 인코딩한 PNG/JPEG)을 가진 DataFrame, 또는 base64 문자열 리스트
출력: 이미지마다 {"boxes": [[x1, y1, x2, y2, conf, cls], ...]} 를 담은 리스트
"""
import base64

import mlflow.models
import mlflow.pyfunc


class Yolo26Detector(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        from ultralytics import YOLO

        self.model = YOLO(context.artifacts["weights"])

    def predict(self, context, model_input, params=None):
        import cv2
        import numpy as np

        params = params or {}
        if hasattr(model_input, "columns"):
            items = list(model_input["image"])
        else:
            items = list(model_input)

        images = []
        for item in items:
            raw = base64.b64decode(item) if isinstance(item, str) else bytes(item)
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("이미지를 디코딩할 수 없습니다")
            images.append(img)

        results = self.model.predict(
            images,
            imgsz=int(params.get("imgsz", 640)),
            conf=float(params.get("conf", 0.25)),
            verbose=False,
        )
        out = []
        for r in results:
            boxes = r.boxes
            rows = []
            if boxes is not None and len(boxes):
                xyxy = boxes.xyxy.cpu().numpy()
                conf = boxes.conf.cpu().numpy()
                cls = boxes.cls.cpu().numpy()
                for b, c, k in zip(xyxy, conf, cls):
                    rows.append([float(b[0]), float(b[1]), float(b[2]), float(b[3]), float(c), int(k)])
            out.append({"boxes": rows})
        return out


# MLflow models-from-code: 이 파일 자체를 모델 정의로 기록합니다(pickle 미사용).
mlflow.models.set_model(Yolo26Detector())
