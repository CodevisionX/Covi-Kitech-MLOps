# 1. PyTorch & CUDA 베이스 이미지
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

ENV PYTHONUNBUFFERED=1
ENV POETRY_VERSION=1.7.1

# 2. 시스템 라이브러리 및 Poetry 설치 (DVC 관련 의존성 제거)
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
RUN poetry install --no-interaction --no-ansi --no-root

# 5. 소스 코드 복사
COPY . /app

RUN chmod +x *.py

# 실행 명령
CMD ["python", "train_yolo.py"]