# training/Dockerfile
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

WORKDIR /app

# 시스템 라이브러리 설치
RUN apt-get update && apt-get install -y libgl1-mesa-glx libglib2.0-0 && rm -rf /var/lib/apt/lists/*

# 필요한 패키지들 (YOLO, EfficientNet용 통합)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 모든 학습 스크립트와 유틸리티 복사
COPY . .

# 실행 권한 부여
RUN chmod +x *.py

# CMD를 비워두거나 기본값만 설정 (백엔드에서 보낸 command가 우선순위를 가짐)
CMD ["python", "train_yolo.py"]