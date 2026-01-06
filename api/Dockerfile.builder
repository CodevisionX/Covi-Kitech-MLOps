# Dockerfile.builder
FROM python:3.10-slim

# 1. 시스템 라이브러리 설치
# MLflow 및 BentoML 내부 파일 처리를 위한 최소한의 라이브러리만 유지합니다.
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. 환경 변수 설정
# 타임아웃을 넉넉히 잡고, BentoML 홈 디렉토리를 공유 볼륨 경로(/root/.bentoml)와 일치시킵니다.
ENV POETRY_HTTP_TIMEOUT=1000 \
    PIP_DEFAULT_TIMEOUT=1000 \
    BENTOML_HOME=/root/.bentoml

# 3. Poetry 설치 (package-mode를 지원하는 1.8.3 버전 사용)
RUN pip install "poetry==1.8.3"

# 4. Poetry 설정 최적화
# 네트워크 안정성을 위해 동시 다운로드 작업자 수를 제한합니다.
RUN poetry config installer.max-workers 4

# 5. 설정 파일 복사
# pyproject.toml과 poetry.lock* 파일을 복사합니다.
COPY pyproject.toml poetry.lock* ./

# 6. 의존성 설치
# [핵심] --without inference 옵션을 사용하여 
# 무거운 AI 라이브러리 설치를 완전히 건너뜁니다.
RUN poetry config virtualenvs.create false \
    && poetry install --no-root --without inference --without dev --no-interaction --no-ansi

# 7. 빌더 전용 실행 스크립트 복사
COPY deploy_worker.py .

# 8. 빌더 실행
CMD ["python", "deploy_worker.py"]