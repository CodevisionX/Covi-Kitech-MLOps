# 1. 빌드 인자 정의 (기본값 설정)
ARG TORCH_VER=2.5.1
ARG CUDA_VER=12.4
# PyTorch 공식 이미지는 Python 버전을 포함하고 있으므로 해당 이미지를 기반으로 합니다.
FROM pytorch/pytorch:${TORCH_VER}-cuda${CUDA_VER}-cudnn9-runtime

ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.7.1 \
    DEBIAN_FRONTEND=noninteractive

# 2. 시스템 라이브러리 및 Poetry 설치
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install "poetry==$POETRY_VERSION"

# 3. Poetry 설정: 시스템 파이썬에 바로 설치
RUN poetry config virtualenvs.create false
WORKDIR /app

# 4. 의존성 파일 복사 및 설치
COPY pyproject.toml poetry.lock* /app/
RUN poetry install --no-interaction --no-ansi --no-root --without ml


# 5. 소스 코드 복사
COPY . /app

RUN chmod +x *.py

# 실행 명령
CMD ["python", "train_yolo.py"]