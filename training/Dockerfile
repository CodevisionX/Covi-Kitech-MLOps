# 1. 빌드 인자 정의
ARG CUDA_VER=12.4
FROM nvidia/cuda:${CUDA_VER}-runtime-ubuntu22.04

ARG PYTHON_VER=3.10
ARG TORCH_VER=2.5.1
ARG CUDA_VER

ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.7.1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 2. 시스템 라이브러리 및 특정 Python 버전 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && apt-get install -y --no-install-recommends \
    python${PYTHON_VER} \
    python${PYTHON_VER}-dev \
    python${PYTHON_VER}-distutils \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    build-essential && \
    curl -sS https://bootstrap.pypa.io/get-pip.py | python${PYTHON_VER} && \
    pip install --no-cache-dir "poetry==$POETRY_VERSION" && \
    rm -rf /var/lib/apt/lists/*

# 3. Poetry 설정: 가상환경 생성 안 함
RUN poetry config virtualenvs.create false

# 4. 의존성 설치 
# 핵심: PyTorch는 시스템 CUDA 버전에 맞춰 pip로 선제 설치 (용량 및 버전 관리)
COPY pyproject.toml poetry.lock* /app/

# CUDA 버전을 파이썬 설치 경로 형식으로 변환 (예: 12.4 -> cu124)
RUN CUDA_TAG=$(echo $CUDA_VER | sed 's/\.//g') && \
    pip install --no-cache-dir \
    torch==${TORCH_VER} \
    torchvision \
    --index-url https://download.pytorch.org/whl/cu${CUDA_TAG}

# 나머지 종속성 설치
RUN poetry install --no-interaction --no-ansi --no-root --without ml

# 5. 소스 코드 복사
COPY . /app
RUN chmod +x *.py

# 실행 명령
CMD ["python3", "train_yolo.py"]