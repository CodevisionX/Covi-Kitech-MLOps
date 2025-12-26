import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "MLOps Platform"

    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "kitech")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "kitech2025!")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "mlflow_db")
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "postgres")

    MINIO_ROOT_USER=os.getenv("MINIO_ROOT_USER", "minio")
    MINIO_ROOT_PASSWORD=os.getenv("MINIO_ROOT_PASSWORD", "minio123")

    MLFLOW_S3_ENDPOINT_URL=os.getenv("MLFLOW_S3_ENDPOINT_URL", "http://minio:9000")
    MLFLOW_TRACKING_URI=os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")

    DATABASE_URL: str = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}:5432/{POSTGRES_DB}"

settings = Settings()