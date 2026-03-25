# 1. NVIDIA NGC PyTorch 이미지 사용 (Blackwell 등 최신 아키텍처 완벽 지원)
FROM nvcr.io/nvidia/pytorch:26.02-py3

ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.7.1 \
    DEBIAN_FRONTEND=noninteractive

# 2. 시스템 라이브러리 및 Poetry 설치
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 3. Poetry 설정 (가상환경 생성 및 시스템 PyTorch 상속 허용)
RUN pip install "poetry==$POETRY_VERSION"
# 가상환경을 프로젝트 폴더 내부에 생성하도록 변경
RUN poetry config virtualenvs.in-project true
# NGC의 강력한 시스템 패키지(PyTorch 등)를 가상환경에서 쓸 수 있게 허용
RUN poetry config virtualenvs.options.system-site-packages true

WORKDIR /app

# 4. 의존성 파일 복사 및 설치 (가상환경인 .venv 내부에 안전하게 설치됨)
COPY pyproject.toml poetry.lock* /app/
RUN poetry install --no-interaction --no-ansi --no-root

# 이후의 모든 명령어(pip, python)가 가상환경을 우선적으로 바라보도록 PATH 설정
ENV PATH="/app/.venv/bin:${PATH}"

# Ultralytics를 가상환경 내부에 추가 설치
RUN pip install --no-cache-dir ultralytics==8.3.0

# 5. 소스 코드 복사
COPY . /app
RUN chmod +x *.py

# NGC 이미지의 PyTorch가 가상환경에서도 잘 인식되는지 확인
RUN python -c "import torch; print(f'NGC PyTorch: {torch.__version__}')"

# 실행 명령
CMD ["python", "--help"]