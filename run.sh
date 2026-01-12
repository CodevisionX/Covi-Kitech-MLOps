#!/bin/bash

# 1. GPU 이름 추출
if ! command -v nvidia-smi &> /dev/null; then
    echo "Not found nvidia-smi. Using Default settings(Ada Lovelace).."
    GPU_NAME="Default"
else
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits | head -n 1)
fi

echo "Detected GPU: $GPU_NAME"

# 2. 아키텍처별 이미지 태그 매핑
# 기본값: Ada Lovelace (RTX 40 시리즈)
TAG="py3.11-torch2.5.1-cuda12.4"

if [[ "$GPU_NAME" == *"RTX 50"* ]] || [[ "$GPU_NAME" == *"Blackwell"* ]]; then
    echo "Architecture: Blackwell detected."
    TAG="py3.11-torch2.9.1-cuda12.8"

elif [[ "$GPU_NAME" == *"RTX 40"* ]] || [[ "$GPU_NAME" == *"Ada"* ]] || [[ "$GPU_NAME" == *"L4"* ]]; then
    echo "Architecture: Ada Lovelace detected."
    TAG="py3.11-torch2.5.1-cuda12.4"

elif [[ "$GPU_NAME" == *"RTX 30"* ]] || [[ "$GPU_NAME" == *"A100"* ]] || [[ "$GPU_NAME" == *"Ampere"* ]] || [[ "$GPU_NAME" == *"A6000"* ]]; then
    echo "Architecture: Ampere detected."
    TAG="py3.11-torch2.4.1-cuda11.8"
fi

# 3. 전체 이미지 이름 구성
REGISTRY="ghcr.io"
REPO_LOWER="codevisionx/covi-kitech-mlops"
FULL_IMAGE_NAME="${REGISTRY}/${REPO_LOWER}-training:${TAG}"

echo "------------------------------------------------------"
echo "Selected Image: $FULL_IMAGE_NAME"
echo "------------------------------------------------------"

# 4. Docker Compose 실행
# .env에 정의된 고정 변수들은 그대로 읽고, TRAINING_IMAGE만 동적으로 주입함
TRAINING_IMAGE="$FULL_IMAGE_NAME" docker compose up -d

echo "------------------------------------------------------"
echo "MLOps Stack is starting up..."
echo "Backend is configured to use the image above for training jobs."