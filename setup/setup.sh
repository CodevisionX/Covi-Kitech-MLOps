#!/bin/bash

echo "=========================================="
echo " KITECH MLOps Platform Setup (Unix/Mac) "
echo "=========================================="

# 0. .env 파일 존재 확인 및 변수 로드
if [ ! -f .env ]; then
    echo "[ERROR] .env file not found!"
    echo "Please make sure .env file exists in the same folder."
    exit 1
fi

echo "[0/4] Loading configurations from .env..."
# .env 파일에서 주석을 제외하고 변수 추출
export $(grep -v '^#' .env | xargs)

# 1. 포트 충돌 확인
echo "[1/4] Checking port availability..."
CONFLICT=0
CHECK_PORTS=($UI_PORT $BACKEND_PORT $MLFLOW_PORT $POSTGRES_PORT $MINIO_PORT $MINIO_CONSOLE_PORT)

for PORT in "${CHECK_PORTS[@]}"; do
    # lsof 또는 netstat을 사용하여 포트 점유 확인
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
        echo "[ERROR] Port $PORT is already in use by another program."
        CONFLICT=1
    fi
done

if [ $CONFLICT -eq 1 ]; then
    echo ""
    echo "Please change the conflicting port values in your .env file and try again."
    exit 1
fi
echo "[OK] All ports are available."

# 2. 필수 폴더 생성 및 권한 부여
echo "[2/4] Creating necessary directories..."
mkdir -p pg_data training_results minio_data
chmod -R 777 training_results pg_data minio_data

# 3. 도커 이미지 로드
echo "[3/4] Loading Docker images from /images folder..."
echo "This may take a few minutes depending on your system performance."
if [ ! -d "images" ]; then
    echo "[ERROR] 'images' folder not found!"
    exit 1
fi

for file in images/*.tar; do
    echo "Loading $file..."
    docker load -i "$file"
done

# 4. 플랫폼 실행
echo "[4/4] Starting MLOps Platform..."
docker compose up -d

echo ""
echo "=========================================="
echo " Setup Complete! "
echo " - Frontend: http://localhost:$UI_PORT"
echo " - Backend: http://localhost:$BACKEND_PORT"
echo " - MLflow: http://localhost:$MLFLOW_PORT"
echo " - MinIO: http://localhost:$MINIO_CONSOLE_PORT (Console)"
echo "=========================================="