# api/Dockerfile
FROM python:3.9-slim

# 1. 시스템 의존성 및 Docker CLI 설치 (가장 안정적인 방식)
# lsb-release를 거치지 않고 직접 docker.io를 설치하여 CLI를 확보합니다.
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    procps \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. 파이썬 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. 소스 코드 복사
COPY . .

# 4. 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]