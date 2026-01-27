import os
import glob
import torch
import torchvision
import mlflow
import bentoml
import numpy as np
from PIL import Image, ImageDraw



class YoloRunnable(bentoml.Runnable):
    SUPPORTED_RESOURCES = ("cpu", "nvidia.com/gpu")
    SUPPORTS_CPU_MULTI_THREADING = True

    def __init__(self, model_tag):
        bento_model = bentoml.models.get(model_tag)
        model_path = os.path.join(bento_model.path, "mlflow_model")

        print(f"DEBUG: BentoML Model Path: {model_path}")
        print(f"DEBUG: Contents of path: {os.listdir(bento_model.path)}")
        
        # MLmodel 경로 탐색
        if not os.path.exists(os.path.join(model_path, "MLmodel")):
            found = glob.glob(os.path.join(bento_model.path, "**/MLmodel"), recursive=True)
            if found: model_path = os.path.dirname(found[0])

        self.model = mlflow.pytorch.load_model(model_path)
        self.model.eval()
        if torch.cuda.is_available():
            self.model.cuda()

    @bentoml.Runnable.method(batchable=False)
    def predict(self, input_array, original_img):
        input_tensor = torch.from_numpy(input_array)
        if torch.cuda.is_available():
            input_tensor = input_tensor.cuda()

        with torch.no_grad():
            preds = self.model(input_tensor)
            if isinstance(preds, tuple): preds = preds[0]

        detections = self.post_process(preds)

        return self.visualize(original_img, detections)

    def post_process(self, preds, conf_thres=0.25, iou_thres=0.45):
        """
        Raw Tensor Output (1, 84, 8400) -> Clean JSON Output 변환
        """
        # 1. (Batch, Ch, Anchors) -> (Batch, Anchors, Ch) 변환
        preds = preds.transpose(1, 2)
        
        outputs = []
        for i, pred in enumerate(preds):
            # 2. 박스 좌표(cx, cy, w, h)와 클래스 확률 분리
            boxes = pred[:, :4] 
            scores = pred[:, 4:] 
            
            # 3. 최대 확률값과 해당 클래스 ID 추출
            class_max_scores, class_ids = torch.max(scores, 1)
            
            # 4. Confidence Threshold 필터링
            mask = class_max_scores > conf_thres
            filtered_boxes = boxes[mask]
            filtered_scores = class_max_scores[mask]
            filtered_class_ids = class_ids[mask]
            
            if len(filtered_boxes) == 0:
                outputs.append([])
                continue

            # 5. 좌표 변환: (cx, cy, w, h) -> (x1, y1, x2, y2)
            xc, yc, w, h = filtered_boxes[:, 0], filtered_boxes[:, 1], filtered_boxes[:, 2], filtered_boxes[:, 3]
            x1 = xc - w / 2
            y1 = yc - h / 2
            x2 = xc + w / 2
            y2 = yc + h / 2
            nms_boxes = torch.stack([x1, y1, x2, y2], dim=1)
            
            # 6. NMS 실행 (중복 박스 제거)
            keep_indices = torchvision.ops.nms(nms_boxes, filtered_scores, iou_thres)
            
            # 7. 최종 결과 리스트 생성 (NameError 해결 지점)
            final_results = []
            for idx in keep_indices:
                final_results.append({
                    "class_id": int(filtered_class_ids[idx]),
                    "confidence": float(filtered_scores[idx]),
                    "box": nms_boxes[idx].tolist() # [x1, y1, x2, y2]
                })
            
            outputs.append(final_results)
            
        return outputs[0] if outputs else []
    
    def visualize(self, original_img, detections):
        """
        이미지 위에 박스를 그리는 내부 메서드
        """
        draw = ImageDraw.Draw(original_img)
        width, height = original_img.size
        scale = 640 # 모델 입력 기준 사이즈

        for det in detections:
            box = det['box']
            # 좌표 복원 (640 기준 -> 원본 크기)
            x1 = box[0] * (width / scale)
            y1 = box[1] * (height / scale)
            x2 = box[2] * (width / scale)
            y2 = box[3] * (height / scale)

            draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
            draw.text((x1, y1 - 10), f"ID:{det['class_id']} {det['confidence']:.2f}", fill="red")
        
        return original_img