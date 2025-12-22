import bentoml
from bentoml.io import Image, JSON
import PIL.Image
from ultralytics import YOLO
import numpy as np

# 1. BentoML 모델 저장소에서 모델 가져오기
# 백엔드 서버에서 모델을 등록할 때 사용할 이름을 지정합니다.
model_ref = bentoml.models.get("yolo_v8_pcb_model:latest")

# 2. 서비스 정의
@bentoml.service(
    name="pcb_defect_detector",
    traffic={"timeout": 30},
    # 제조 현장의 고성능 처리를 위해 워커 수 등을 조절할 수 있습니다.
)
class YoloService:
    def __init__(self):
        # BentoML 모델 경로에서 실제 YOLOv8 모델 로드
        # model_ref.path_of("model.pt")는 패키징된 가중치 파일의 경로를 반환합니다.
        self.model = YOLO(model_ref.path_of("model.pt"))
        print("✅ YOLOv8 모델이 BentoML 서비스에 로드되었습니다.")

    @bentoml.api(input=Image(), output=JSON())
    def predict(self, img: PIL.Image.Image):
        """
        이미지를 입력받아 결함 탐지 결과를 반환합니다.
        """
        # 1. 추론 수행
        # YOLOv8은 PIL 이미지를 바로 입력받을 수 있습니다.
        results = self.model.predict(img, conf=0.25) # 임계값 설정 가능
        
        # 2. 결과 가공
        output = []
        for result in results:
            boxes = result.boxes
            for box in boxes:
                # 좌표, 신뢰도, 클래스 추출
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf)
                cls_id = int(box.cls)
                cls_name = self.model.names[cls_id]
                
                output.append({
                    "box": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
                    "confidence": round(conf, 4),
                    "class_id": cls_id,
                    "class_name": cls_name
                })

        return {"defects": output, "count": len(output)}