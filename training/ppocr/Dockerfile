# PP-OCRv6 문자 인식 모델 학습 이미지
# 빌드 컨텍스트: ./training  (docker build -f training/ppocr/Dockerfile training)
#
# CUDA_FLAVOR: PaddlePaddle GPU wheel 의 CUDA 빌드
#   cu126 (기본) - 고객 배포 환경(RTX A4000, CUDA 12.6)과 동일
#   cu129 / cu130 - Blackwell(RTX 50xx) 등 최신 GPU
FROM python:3.10-slim

ARG CUDA_FLAVOR=cu126
ARG PADDLE_VERSION=3.3.1
# 고객이 사용한 PaddleOCR 학습 엔진과 동일한 공식 커밋 (3.8.0.dev9+g211989f04)
ARG PADDLEOCR_COMMIT=211989f046cc1878460f9e65574690c00a127a1a
# 공식 사전학습 가중치 (고객 제공 파일과 SHA-256 동일함을 확인)
ARG PPOCRV6_MEDIUM_URL=https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv6_medium_rec_pretrained.pdparams
ARG PPOCRV6_MEDIUM_SHA256=c4a110423c23739f157ff870e27f41649d8c89e4c8df5230c2cd2e9fd90a7e92

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    FLAGS_use_mkldnn=0 \
    PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=0 \
    PADDLEOCR_ROOT=/opt/PaddleOCR \
    PRETRAINED_DIR=/opt/pretrained

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libgomp1 git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}"

RUN pip install --upgrade pip \
    && pip install "paddlepaddle-gpu==${PADDLE_VERSION}" \
       -i "https://www.paddlepaddle.org.cn/packages/stable/${CUDA_FLAVOR}/" \
       --extra-index-url https://pypi.org/simple

COPY ppocr/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# 학습 엔진: 공식 저장소의 고정 커밋 (configs / ppocr / tools 사용)
RUN git init -q "$PADDLEOCR_ROOT" \
    && git -C "$PADDLEOCR_ROOT" remote add origin https://github.com/PaddlePaddle/PaddleOCR.git \
    && git -C "$PADDLEOCR_ROOT" fetch -q --depth 1 origin "$PADDLEOCR_COMMIT" \
    && git -C "$PADDLEOCR_ROOT" checkout -q FETCH_HEAD \
    && rm -rf "$PADDLEOCR_ROOT/.git"

RUN mkdir -p "$PRETRAINED_DIR" \
    && curl -fsSL -o "$PRETRAINED_DIR/PP-OCRv6_medium_rec_pretrained.pdparams" "$PPOCRV6_MEDIUM_URL" \
    && echo "${PPOCRV6_MEDIUM_SHA256}  $PRETRAINED_DIR/PP-OCRv6_medium_rec_pretrained.pdparams" | sha256sum -c -

WORKDIR /app
ENV CUDA_FLAVOR=${CUDA_FLAVOR} \
    PADDLEOCR_COMMIT=${PADDLEOCR_COMMIT}
COPY utils.py mlops_common.py dataset_tools.py validate_dataset.py /app/
COPY ppocr/ /app/

# paddle 은 import 시 GPU 드라이버(libcuda)가 필요하므로 빌드 단계에서는 설치 버전만 확인합니다.
RUN python -c "import importlib.metadata as m; print({p: m.version(p) for p in ['paddlepaddle-gpu', 'mlflow', 'numpy', 'opencv-python']})"

RUN python -c "import train_ppocr"

CMD ["python", "train_ppocr.py"]
