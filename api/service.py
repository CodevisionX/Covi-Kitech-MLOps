import os
import io
import bentoml
import numpy as np
from PIL import Image
from runnables.yolo_runnable import YoloRunnable
from runnables.cnn_runnable import CnnRunnable

BENTO_MODEL_TAG = os.environ.get("BENTOML_MODEL_TAG")
bento_model = bentoml.models.get(BENTO_MODEL_TAG)

print(f"DEBUG: All Labels -> {bento_model.info.labels}")
print(f"DEBUG: All Metadata -> {bento_model.info.metadata}")

# 모델 메타데이터에서 타입 확인 (YOLO인지 CNN인지)
model_type = (
    bento_model.info.labels.get("model_type") or 
    bento_model.info.metadata.get("model_type") or 
    "yolo"
)
print(f"DEBUG: Selected model_type -> {model_type}")

# 1. 모델 타입에 맞는 Runner 생성
if "yolo" in str(model_type).lower():
    model_runner = bentoml.Runner(YoloRunnable, name="yolo_runner", runnable_init_params={"model_tag": BENTO_MODEL_TAG})
    svc = bentoml.Service("yolo_inference_service", runners=[model_runner])

    @svc.api(
        input=bentoml.io.Image(), 
        output=bentoml.io.Image(),
        route="/predict",
        doc="""
### [YOLOv8] 객체 탐지 규격
이미지 파일(JPG/PNG)을 직접 업로드하여 추론을 수행합니다.

**입력 데이터 구조:**
- **입력**: 3채널 RGB 이미지 (자동 리사이즈: 640x640)
- **추론 방식**: (1, 3, 640, 640) 텐서 변환 후 NMS 적용

**출력 데이터 구조:**
- `status`: 처리 결과 (success)
- `type`: 서비스 유형 (detection)
- `prediction`: 탐지된 객체 정보 리스트
  - `class_id`: 탐지된 객체의 인덱스
  - `confidence`: 탐지 확률 (0.0 ~ 1.0)
  - `box`: [x1, y1, x2, y2] 형식의 좌표
        """
    )
    async def predict_yolo(input_img: Image.Image):
        original_img = input_img.convert("RGB")
        original_img.format = input_img.format or "JPEG"

        resized_img = original_img.resize((640, 640))
        img_array = np.array(resized_img).transpose(2, 0, 1)
        img_array = np.expand_dims(img_array, axis=0).astype(np.float32) / 255.0
        
        result_img = await model_runner.predict.async_run(img_array, original_img)
        return result_img
    
else:
    model_runner = bentoml.Runner(CnnRunnable, name="cnn_runner", runnable_init_params={"model_tag": BENTO_MODEL_TAG})
    svc = bentoml.Service("cnn_inference_service", runners=[model_runner])

    @svc.api(
        input=bentoml.io.File(), 
        output=bentoml.io.JSON(), 
        route="/utils/extract-sample",
        doc="""
### 검증용 샘플 추출기
학습 데이터(`X.npy`)를 업로드하여 `/predict` API용 JSON 샘플을 생성합니다.
        """
    )
    def extract_npy_sample(input_file: bentoml.io.File):
        try:
            file_content = input_file.read()
            data = np.load(io.BytesIO(file_content))

            num_total = data.shape[0]
            window_size = data.shape[1] if len(data.shape) > 1 else 0
            
            if window_size > 1:
                # 시계열 흐름이 있는 데이터 (TEP 등)
                size = min(num_total, 3)
                start_idx = np.random.randint(0, num_total - size + 1)
                indices = list(range(start_idx, start_idx + size))
                mode = "Sequential (Window > 1)"
            else:
                # 단일 시점 데이터 (Gas Turbine 등)
                size = min(num_total, 3)
                indices = np.random.choice(num_total, size=size, replace=False).tolist()
                mode = "Random (Window = 1)"

            sample_data = data[indices].tolist()
            return {
                "status": "success",
                "sampling_mode": mode,
                "extracted_indices": indices,
                "shape": str(data.shape),
                "data": sample_data
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    @svc.api(
        input=bentoml.io.JSON(), 
        output=bentoml.io.JSON(), 
        route="/predict",
        doc="""
### 1D-CNN 산업 데이터 분석 API 규격 (통합 가이드)
본 API는 시계열 수치 데이터를 입력받아 산업 공정의 이상 상태를 진단하거나 환경 배출 수치를 예측합니다. 
현재 배포된 모델의 종류(TEP 또는 Gas Turbine)에 맞춰 아래 규격에 따라 데이터를 전송하십시오.

---

#### **CASE 1: [TEP] 공정 이상 분류 (Classification)**
텐네시 이스트만 공정(TEP)의 센서 데이터를 분석하여 21가지 고장 유형을 탐지합니다.

- **입력 데이터**:
    - **형상(Shape)**: (Batch, 20, 52)
    - **구조**: 20개의 타임스텝(Window) 동안 수집된 52개의 공정 변수(원재료 유량, 반응기 온도/압력 등)가 필요합니다.
- **출력 결과**:
    - `0`: 정상 운전 (Normal Operation)
    - `1 ~ 21`: 특정 고장 유형 (예: Fault 1 - Feed Ratio Change)
- **JSON 데이터 예시**:
```json
{
  "data": [
    [
      [v1, v2, ..., v52],  // t-19 시점
      [v1, v2, ..., v52],  // t-18 시점
      ...
      [v1, v2, ..., v52]   // t (현재 시점)
    ]
  ]
}
```
---

#### **CASE 2: [Gas Turbine] 배출가스 예측 (Regression/Classification)**
가스 터빈의 운전 데이터를 바탕으로 배출가스 농도 및 운전 등급을 예측합니다.

- **입력 데이터**:
    - **형상(Shape)**: (Batch, 1, 9)
    - **구조**: 윈도우 크기는 1이며, 주변 온도(AT), 압력(AP), 습도(AH) 등 9개의 핵심 피처를 포함해야 합니다.
- **출력 결과**:
    - 분류 모델인 경우: 1(최적), 2(주의), 3(위험) 등급 반환
    - 회귀 모델인 경우: 실제 예측된 농도 수치값(CO, NOX) 반환
- **JSON 데이터 예시**:
```json
{
  "data": [
    [ [AT, AP, AH, AFDP, GTEP, TIT, TAT, TEY, CDP] ]
  ]
}

주의사항: 모든 입력 데이터는 학습 시 사용된 스케일러(StandardScaler 등)로 정규화된 상태여야 정확한 분석 결과가 도출됩니다.
```
---
"""
    )
    async def predict_cnn(input_data: dict):
        # 1. 입력 데이터 준비
        data_array = np.array(input_data['data']).astype(np.float32)

        # 2. 추론 수행
        result = await model_runner.predict.async_run(data_array)

        indices = input_data.get('extracted_indices', "Unknown")

        is_regression = result.ndim > 1 and result.shape[1] == 1 or "regression" in str(model_type).lower()
        
        return {
        "status": "success",
        "type": "regression" if is_regression else "classification",
        "metadata": {
            "source_indices": indices,
            "input_shape": str(data_array.shape)
        },
        "prediction": result.tolist()
    }