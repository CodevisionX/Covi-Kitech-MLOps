# 1. 빌드 인자 정의
ARG CUDA_VER=12.4.1
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

# 4. 의존성 설치 (가장 효율적인 방식)
COPY pyproject.toml poetry.lock* /app/

# Poetry에서 리스트만 뽑아서 pip로 설치 (충돌 방지 및 그룹 에러 차단)
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes && \
    pip install --no-cache-dir -r requirements.txt && \
    rm requirements.txt  # 임시 파일 삭제

# GPU 버전에 맞는 PyTorch 설치 (최종 단계에 배치하여 캐시 활용)
RUN CUDA_TAG=$(echo $CUDA_VER | cut -d'.' -f1,2 | sed 's/\.//g') && \
    pip install --no-cache-dir \
    torch==${TORCH_VER} \
    torchvision \
    --index-url https://download.pytorch.org/whl/cu${CUDA_TAG}

# 5. 소스 코드 복사
COPY . /app
RUN chmod +x *.py

# 실행 명령
CMD ["python3", "train_yolo.py"]