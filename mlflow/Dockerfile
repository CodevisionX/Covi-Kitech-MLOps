# mlflow/Dockerfile
# MLflow 3.x 는 Python 3.10 이상이 필요합니다.
FROM python:3.11-slim

# 백엔드·학습·Jupyter 와 같은 MLflow 버전을 사용합니다.
# SQLAlchemy 2.1+ 는 postgresql:// 에 psycopg(3) 를 기본 드라이버로 사용합니다.
RUN pip install --no-cache-dir mlflow==3.17.2 boto3 "psycopg[binary]" psycopg2-binary

COPY entrypoint.sh /usr/local/bin/mlflow-entrypoint.sh
RUN chmod +x /usr/local/bin/mlflow-entrypoint.sh

# 기존(2.x) DB 스키마가 있으면 서버 시작 전에 업그레이드합니다.
ENTRYPOINT ["/usr/local/bin/mlflow-entrypoint.sh"]

# 실행 명령 (docker-compose에서 오버라이딩 가능하지만 기본값 설정)
CMD ["mlflow", "server", \
     "--host", "0.0.0.0", \
     "--port", "5000"]
