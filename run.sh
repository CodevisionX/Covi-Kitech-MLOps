#!/bin/bash

# 1. GPU 이름 추출
if ! command -v nvidia-smi &> /dev/null; then
    echo "Warning: nvidia-smi not found. Using Default settings..."
    GPU_NAME="Default"
else
    # GPU 이름을 추출하여 변수에 저장
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits | head -n 1)
fi

echo "Detected GPU: $GPU_NAME"

# 2. 아키텍처별 이미지 태그 매핑
DEFAULT_TAG="py3.11-torch2.5.1-cuda12.4"
TAG=$DEFAULT_TAG

if [[ "$GPU_NAME" == *"Blackwell"* ]] || [[ "$GPU_NAME" == *"RTX 50"* ]]; then
    echo "Architecture: Blackwell detected."
    TAG="py3.11-torch2.9.1-cuda12.8"

elif [[ "$GPU_NAME" == *"H100"* ]] || [[ "$GPU_NAME" == *"H200"* ]] || [[ "$GPU_NAME" == *"Hopper"* ]]; then
    echo "Architecture: Hopper detected."
    TAG="py3.11-torch2.5.1-cuda12.4"

elif [[ "$GPU_NAME" == *"Ada"* ]] || [[ "$GPU_NAME" == *"RTX 40"* ]] || [[ "$GPU_NAME" == *"L4"* ]]; then
    echo "Architecture: Ada Lovelace detected."
    TAG="py3.11-torch2.5.1-cuda12.4"

elif [[ "$GPU_NAME" == *"Ampere"* ]] || [[ "$GPU_NAME" == *"A100"* ]] || [[ "$GPU_NAME" == *"RTX 30"* ]] || [[ "$GPU_NAME" == *"A"* ]]; then
    echo "Architecture: Ampere detected."
    TAG="py3.11-torch2.4.1-cuda11.8"

elif [[ "$GPU_NAME" == *"Turing"* ]] || [[ "$GPU_NAME" == *"RTX 20"* ]] || [[ "$GPU_NAME" == *"T4"* ]]; then
    echo "Architecture: Turing detected."
    TAG="py3.11-torch2.4.1-cuda11.8"

else
    # 위 조건 어디에도 해당하지 않는 경우 (예: CPU 환경, 구형 Pascal/Maxwell GPU 등)
    echo "------------------------------------------------------"
    echo "Notice: No specific architecture match found for '$GPU_NAME'."
    echo "Applying Default Base Image: $DEFAULT_TAG"
    echo "------------------------------------------------------"
    TAG=$DEFAULT_TAG
fi

# 3. 전체 이미지 이름 구성
REGISTRY="ghcr.io"
REPO_LOWER="codevisionx/covi-kitech-mlops"
FULL_IMAGE_NAME="${REGISTRY}/${REPO_LOWER}-training:${TAG}"

echo "------------------------------------------------------"
echo "Selected Image: $FULL_IMAGE_NAME"
echo "------------------------------------------------------"

# 4. Docker Compose 실행
# TRAINING_IMAGE 변수를 주입하여 컨테이너 실행
TRAINING_IMAGE="$FULL_IMAGE_NAME" docker compose up -d

echo "------------------------------------------------------"
echo "MLOps Stack is starting up..."
echo "Backend is configured to use the image above for training jobs."