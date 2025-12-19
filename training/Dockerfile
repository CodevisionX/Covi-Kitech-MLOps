# 1. PyTorch & CUDA가 이미 세팅된 이미지를 사용
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

# ✅ 파이썬 로그 버퍼링 해제 (실시간 로그 출력용)
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 시스템 라이브러리 (YOLO/OpenCV용)
RUN apt-get update && apt-get install -y libgl1-mesa-glx libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 실행 권한 부여
RUN chmod +x *.py

CMD ["python", "train_yolo.py"]