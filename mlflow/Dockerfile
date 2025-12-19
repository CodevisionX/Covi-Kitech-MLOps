# mlflow/Dockerfile
FROM python:3.9-slim

# 필수 패키지 설치
RUN pip install mlflow==2.14.0 boto3 psycopg2-binary

# 실행 명령 (docker-compose에서 오버라이딩 가능하지만 기본값 설정)
CMD ["mlflow", "server", \
     "--host", "0.0.0.0", \
     "--port", "5000"]