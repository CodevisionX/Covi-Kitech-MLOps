import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "MLOps Platform"

    # 기본값은 두되, pydantic이 실제 환경변수가 있으면 알아서 우선순위를 가집니다.
    POSTGRES_USER: str = "kitech"
    POSTGRES_PASSWORD: str = "kitech2025!"
    POSTGRES_DB: str = "mlflow_db"
    POSTGRES_SERVER: str = "postgres"

    MINIO_ROOT_USER: str = "minio"
    MINIO_ROOT_PASSWORD: str = "minio123"

    MLFLOW_S3_ENDPOINT_URL: str = "http://mlops-minio:9000"
    MLFLOW_TRACKING_URI: str = "http://mlflow:5000"

    MAX_DEPLOYMENTS_PER_PROJECT: int = 3

    # [수정] 클래스 변수가 아닌 프로퍼티로 선언하여 최신 값을 반영하도록 함
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:5432/{self.POSTGRES_DB}"

    class Config:
        case_sensitive = True # 대소문자 구분 (권장)

settings = Settings()