#!/bin/bash

# 저장할 폴더 생성
mkdir -p images_compressed

echo "=========================================="
echo "   KITECH MLOps Image Compressor (.sh)    "
echo "=========================================="

# 이미지 리스트 정의 (이름:파일명)
declare -A images=(
    ["mlops_kitech-backend:latest"]="backend.tar.gz"
    ["mlops_kitech-mlflow:latest"]="mlflow.tar.gz"
    ["mlops_kitech-ui:latest"]="ui.tar.gz"
    ["mlops_kitech-training:latest"]="training.tar.gz"
    ["mlops-builder:latest"]="builder.tar.gz"
    ["bentoml-generic-server:latest"]="base_server.tar.gz"
    ["postgres:13"]="postgres.tar.gz"
    ["minio/minio:latest"]="minio.tar.gz"
)

for img in "${!images[@]}"; do
    filename=${images[$img]}
    echo ">>> Saving and Compressing $img ..."
    # 핵심: docker save 출력을 바로 gzip으로 넘겨 파일로 저장
    docker save "$img" | gzip > "images_compressed/$filename"
done

echo "=========================================="
echo "   Compression Complete! (Folder: images_compressed) "
echo "=========================================="