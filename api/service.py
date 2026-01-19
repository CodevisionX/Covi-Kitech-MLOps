import os
import glob
import bentoml
import numpy as np
import torch
import torchvision  # NMS 처리를 위해 필수
import mlflow
from PIL import Image, ImageDraw, ImageFont

SERVICE_DESCRIPTION = """
## YOLOv8 기반 실시간 객체 탐지 서비스 (MLOps)
이 서비스는 YOLOv8 모델을 사용하여 이미지 내의 객체를 탐지합니다.
두 가지 방식의 API를 제공합니다:
1. **JSON 기반 데이터 추출**: 탐지된 객체의 좌표와 확률 정보를 반환 (자동화 시스템용)
2. **시각화 이미지 반환**: 이미지 위에 바운딩 박스를 그려서 반환 (모니터링/확인용)

**참고:** 모든 입력 이미지는 모델 추론 전 내부적으로 640x640 사이즈로 리사이즈됩니다.
"""

# 1. 환경 변수 체크
BENTO_MODEL_TAG = os.environ.get("BENTOML_MODEL_TAG")
if not BENTO_MODEL_TAG:
    raise RuntimeError("BENTOML_MODEL_TAG 환경 변수가 설정되지 않았습니다.")

# 2. Custom Runnable 정의
class YoloRunnable(bentoml.Runnable):
    SUPPORTED_RESOURCES = ("cpu", "nvidia.com/gpu")
    SUPPORTS_CPU_MULTI_THREADING = True

    def __init__(self):
        # 1. 모델 참조 가져오기
        bento_model = bentoml.models.get(BENTO_MODEL_TAG)
        model_path = bento_model.path

        # 2. MLmodel 파일이 있는 실제 경로 찾기
        if not os.path.exists(os.path.join(model_path, "MLmodel")):
            found_files = glob.glob(os.path.join(model_path, "**/MLmodel"), recursive=True)
            if found_files:
                model_path = os.path.dirname(found_files[0])
                print(f"[YoloRunnable] Found MLmodel at: {model_path}")
            else:
                print(f"[Error] Files in {bento_model.path}: {os.listdir(bento_model.path)}")
                raise FileNotFoundError(f"Cannot find MLmodel file inside {bento_model.path}")

        # 3. 모델 로드
        print(f"[YoloRunnable] Loading model from {model_path}...")
        self.model = mlflow.pytorch.load_model(model_path)
        
        # 4. 평가 모드 및 GPU 설정
        self.model.eval()
        if torch.cuda.is_available():
            self.model.cuda()
            print("[YoloRunnable] Model loaded on GPU")
        else:
            print("[YoloRunnable] Model loaded on CPU")

    @bentoml.Runnable.method(batchable=False)
    def predict(self, input_array):
        print(f"[Debug] Input shape: {input_array.shape}, Max val: {input_array.max()}, Min val: {input_array.min()}")

        # Numpy -> Tensor 변환
        input_tensor = torch.from_numpy(input_array)
        
        if torch.cuda.is_available():
            input_tensor = input_tensor.cuda()

        with torch.no_grad():
            # 모델 추론
            preds = self.model(input_tensor)
            
            # [튜플 처리] 결과가 튜플이면 첫 번째 요소만 추출
            if isinstance(preds, tuple):
                preds = preds[0]

            print(f"[Debug] Raw prediction shape: {preds.shape}")

        # [후처리] NMS 적용하여 사람이 읽을 수 있는 결과로 변환
        return self.post_process(preds)

    def post_process(self, preds, conf_thres=0.25, iou_thres=0.45):
        """
        Raw Tensor Output (1, 84, 8400) -> Clean JSON Output 변환 함수
        """
        # (Batch, Ch, Anchors) -> (Batch, Anchors, Ch) 로 변경
        # 예: (1, 84, 8400) -> (1, 8400, 84)
        preds = preds.transpose(1, 2)
        
        outputs = []
        
        # 배치 크기만큼 반복 (보통 1장)
        for i, pred in enumerate(preds):
            # pred shape: (8400, 84)
            
            # 1. 박스 좌표와 클래스 확률 분리
            # YOLO output: [cx, cy, w, h, class1_conf, class2_conf, ...]
            boxes = pred[:, :4] 
            scores = pred[:, 4:] 
            
            # 2. 각 앵커별로 가장 높은 클래스 확률 찾기
            class_max_scores, class_ids = torch.max(scores, 1)

            max_conf_found = class_max_scores.max().item()
            print(f"[Debug] Max confidence found in this image: {max_conf_found:.4f}")
            
            # 3. Confidence Threshold 필터링 (0.25 미만 제거)
            mask = class_max_scores > conf_thres
            filtered_boxes = boxes[mask]
            filtered_scores = class_max_scores[mask]
            filtered_class_ids = class_ids[mask]
            
            if len(filtered_boxes) == 0:
                print("[Debug] No boxes detected after thresholding.")
                outputs.append([])
                continue

            # 4. Box 좌표 변환: (cx, cy, w, h) -> (x1, y1, x2, y2)
            xc, yc, w, h = filtered_boxes[:, 0], filtered_boxes[:, 1], filtered_boxes[:, 2], filtered_boxes[:, 3]
            x1 = xc - w / 2
            y1 = yc - h / 2
            x2 = xc + w / 2
            y2 = yc + h / 2
            
            # NMS를 위해 쌓기
            nms_boxes = torch.stack([x1, y1, x2, y2], dim=1)
            
            # 5. NMS 실행 (겹치는 박스 중 가장 확실한 것만 남김)
            keep_indices = torchvision.ops.nms(nms_boxes, filtered_scores, iou_thres)
            
            print(f"[Debug] Final detections after NMS: {len(keep_indices)}")

            # 6. 최종 결과 리스트 생성
            final_results = []
            for idx in keep_indices:
                final_results.append({
                    "class_id": int(filtered_class_ids[idx]),
                    "confidence": float(filtered_scores[idx]),
                    "box": nms_boxes[idx].tolist() # [x1, y1, x2, y2]
                })
            
            outputs.append(final_results)
            
        return outputs[0] # 배치 첫 번째 결과 반환

# 3. Runner 생성
yolo_runner = bentoml.Runner(YoloRunnable, name="yolo_runner")

# 4. 서비스 정의
svc = bentoml.Service("yolo_mlops_service", runners=[yolo_runner])


@svc.api(
    input=bentoml.io.Image(), 
    output=bentoml.io.JSON(),
    route="/predict/data",
    doc="""
### 객체 탐지 결과 (JSON)ㅎㅎ
업로드된 이미지에서 객체를 찾아 좌표와 클래스 정보를 JSON 형태로 반환합니다.

**추론 프로세스:**
- 이미지 RGB 변환 및 640x640 리사이즈
- 정규화 (0~1) 및 NMS(Non-Maximum Suppression) 적용

**응답 데이터 구조:**
- `status`: 요청 처리 상태 (success/error)
- `model_tag`: 추론에 사용된 모델의 BentoML 태그
- `prediction`: 탐지된 객체 리스트
    - `class_id`: 객체 카테고리 인덱스
    - `confidence`: 탐지 확신도 (0.0 ~ 1.0)
    - `box`: [x1, y1, x2, y2] (640x640 기준 좌표)
    """
)
async def predict_data(input_img: Image.Image):
    # 흑백/투명 배경 이미지가 들어와도 강제로 3채널(RGB)로 변환
    input_img = input_img.convert("RGB")
    
    # 리사이즈 (모델 학습 사이즈에 맞춤)
    input_img = input_img.resize((640, 640))
    
    # 이미지 -> 넘파이 배열
    img_array = np.array(input_img)
    
    # (H, W, C) -> (C, H, W)
    img_array = img_array.transpose(2, 0, 1)
    
    # 배치 차원 추가: (1, C, H, W)
    img_array = np.expand_dims(img_array, axis=0)
    
    # 정규화
    img_array = img_array.astype(np.float32) / 255.0
    
    # Runner 실행
    result = await yolo_runner.predict.async_run(img_array)
    
    return {
        "status": "success",
        "model_tag": BENTO_MODEL_TAG,
        "prediction": result
    }

@svc.api(
    input=bentoml.io.Image(), 
    output=bentoml.io.Image(),
    route="/predict/visual", # 경로를 조금 더 직관적으로 변경
    doc="""
### 시각화된 이미지 반환
이미지 위에 탐지된 객체의 **바운딩 박스(Red Line)**와 **라벨**을 그려서 이미지 파일 자체를 반환합니다.

**주요 특징:**
- 원본 이미지 크기에 맞춰 좌표가 복원(Rescale)되어 그려집니다.
- 별도의 파싱 없이 결과를 즉시 이미지 뷰어로 확인할 때 유용합니다.
- 출력 포맷: 입력과 동일한 이미지 포맷 (JPG/PNG 등)
    """
)
async def predict_visual(input_img: Image.Image):
    
    input_img = input_img.convert("RGB")

    # 1. 원본 사이즈 저장
    original_width, original_height = input_img.size
    
    # 2. 전처리 (모델 입력 크기 640x640)
    input_size = 640
    resized_img = input_img.resize((input_size, input_size))
    img_array = np.array(resized_img).transpose(2, 0, 1)
    img_array = np.expand_dims(img_array, axis=0).astype(np.float32) / 255.0
    
    # 3. Runner 실행 (좌표 결과 가져오기)
    predictions = await yolo_runner.predict.async_run(img_array)
    
    # 4. 이미지 위에 그리기 준비
    # 원본 이미지 위에 그릴 것인지, 리사이즈된 이미지 위에 그릴 것인지 선택
    # 여기서는 원본 이미지 위에 그리는 방식으로 진행합니다.
    draw = ImageDraw.Draw(input_img)
    
    # 스케일 계산
    x_scale = original_width / input_size
    y_scale = original_height / input_size

    for det in predictions:
        box = det['box'] # [x1, y1, x2, y2]
        conf = det['confidence']
        cls_id = det['class_id']

        # 좌표를 원본 이미지 크기로 복원
        x1 = box[0] * x_scale
        y1 = box[1] * y_scale
        x2 = box[2] * x_scale
        y2 = box[3] * y_scale

        # 박스 그리기 (색상: 빨강, 두께: 3)
        draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
        
        # 라벨 텍스트 그리기
        label = f"ID: {cls_id} ({conf:.2f})"
        draw.text((x1, y1 - 10), label, fill="red")

    return input_img # 박스가 그려진 이미지 반환
