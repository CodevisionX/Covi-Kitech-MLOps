# PyTorch 학습 이미지: YOLO 계열 검출(YOLO26, YOLOv8) + 시계열 1D-CNN
# 빌드 컨텍스트: ./training  (docker build -f training/yolo26/Dockerfile training)
#
# CUDA_FLAVOR: PyTorch wheel 의 CUDA 빌드
#   cu126 (기본) - 고객 배포 환경(RTX A4000, CUDA 12.6)과 동일
#   cu129 / cu130 - Blackwell(RTX 50xx) 등 최신 GPU (cu126 빌드는 sm_120 미지원)
FROM python:3.10-slim

ARG CUDA_FLAVOR=cu126
ARG TORCH_VERSION=2.13.0
ARG TORCHVISION_VERSION=0.28.0
# 공식 사전학습 가중치 (고객 제공 파일과 SHA-256 동일함을 확인)
ARG YOLO26N_URL=https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt
ARG YOLO26N_SHA256=9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef
# YOLOv8 학습 시작 가중치 (ultralytics 공식 배포본, v8.3.0·v8.4.0 릴리스 파일 동일)
ARG YOLOV8N_URL=https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n.pt
ARG YOLOV8N_SHA256=f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    YOLO_CONFIG_DIR=/opt/ultralytics \
    PRETRAINED_DIR=/opt/pretrained

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 백엔드가 /app/.venv/bin/python 으로 학습 스크립트를 실행합니다.
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}"

RUN pip install --upgrade pip \
    && pip install "torch==${TORCH_VERSION}+${CUDA_FLAVOR}" "torchvision==${TORCHVISION_VERSION}+${CUDA_FLAVOR}" \
       --index-url "https://download.pytorch.org/whl/${CUDA_FLAVOR}"

COPY yolo26/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

RUN mkdir -p "$PRETRAINED_DIR" \
    && curl -fsSL -o "$PRETRAINED_DIR/yolo26n.pt" "$YOLO26N_URL" \
    && echo "${YOLO26N_SHA256}  $PRETRAINED_DIR/yolo26n.pt" | sha256sum -c - \
    && curl -fsSL -o "$PRETRAINED_DIR/yolov8n.pt" "$YOLOV8N_URL" \
    && echo "${YOLOV8N_SHA256}  $PRETRAINED_DIR/yolov8n.pt" | sha256sum -c -

# 인터넷이 막힌 현장에서도 학습되도록 ultralytics 가 실행 중 받는 파일을 미리 준비합니다.
# - 그래프용 폰트(Arial*.ttf), AMP 검사용 yolo26n.pt(weights_dir 에서 찾음)
# - 컨테이너를 root 가 아닌 사용자로 실행해도 쓸 수 있도록 설정 폴더 권한을 엽니다.
RUN mkdir -p "$YOLO_CONFIG_DIR" \
    && curl -fsSL -o "$YOLO_CONFIG_DIR/Arial.ttf" https://ultralytics.com/assets/Arial.ttf \
    && curl -fsSL -o "$YOLO_CONFIG_DIR/Arial.Unicode.ttf" https://ultralytics.com/assets/Arial.Unicode.ttf \
    && python -c "from ultralytics import settings; settings.update(weights_dir='$PRETRAINED_DIR', sync=False)" \
    && chmod -R a+rwX "$YOLO_CONFIG_DIR"

WORKDIR /app
ENV CUDA_FLAVOR=${CUDA_FLAVOR}
COPY utils.py mlops_common.py dataset_tools.py validate_dataset.py evaluate_e2e.py import_model.py /app/
COPY yolo26/ /app/
COPY cnn1d/ /app/

RUN python -c "import torch, ultralytics, mlflow; print('torch', torch.__version__, 'cuda', torch.version.cuda, '| ultralytics', ultralytics.__version__, '| mlflow', mlflow.__version__)"

RUN python -c "import train_yolo26, train_cnn1d, evaluate_e2e, import_model"

CMD ["python", "train_yolo26.py"]
