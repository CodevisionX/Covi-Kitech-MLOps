# api/Dockerfile
FROM python:3.10-slim

WORKDIR /app

# 도커 클라이언트 설치 (컨테이너 제어용)
RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]