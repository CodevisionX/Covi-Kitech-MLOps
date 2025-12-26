FROM python:3.10-slim

# 1. 시스템 의존성 설치 (psycopg2 등을 위한 빌드 도구)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Poetry 설치
ENV POETRY_VERSION=1.7.1
RUN pip install "poetry==$POETRY_VERSION"

# 3. Poetry 설정: 가상환경을 컨테이너 내부에 만들지 않음 (도커 자체가 격리된 환경이므로)
RUN poetry config virtualenvs.create false

WORKDIR /app

# 4. 의존성 파일만 먼저 복사 (캐싱 활용)
COPY pyproject.toml poetry.lock* /app/

# 5. 의존성 설치
# --no-root: 현재 프로젝트(api)를 패키지처럼 설치하지 않음
RUN poetry install --no-interaction --no-ansi --no-root

# 6. 소스 코드 복사
COPY . /app

EXPOSE 8000

# 실행 명령은 docker-compose에서 덮어쓰므로 생략 가능하나 기본값 설정
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]