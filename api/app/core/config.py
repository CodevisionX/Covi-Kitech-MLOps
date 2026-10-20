import os
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "MLOps Platform"

    # 기본값은 두되, pydantic이 실제 환경변수가 있으면 알아서 우선순위를 가집니다.
    POSTGRES_USER: str = "kitech"
    # 비밀번호는 코드에 기본값을 두지 않고 반드시 환경 변수(.env)로 주입
    POSTGRES_PASSWORD: str = Field(min_length=1)
    POSTGRES_DB: str = "mlflow_db"
    POSTGRES_SERVER: str = "postgres"

    # S3 호환 스토리지(RustFS) 접속 정보.
    # S3_* 가 없으면 AWS_* 를 사용하고, v1 의 MINIO_ROOT_* 도 하위 호환으로 받습니다.
    S3_ACCESS_KEY: str = Field(
        min_length=1,
        validation_alias=AliasChoices("S3_ACCESS_KEY", "AWS_ACCESS_KEY_ID", "MINIO_ROOT_USER"),
    )
    S3_SECRET_KEY: str = Field(
        min_length=1,
        validation_alias=AliasChoices("S3_SECRET_KEY", "AWS_SECRET_ACCESS_KEY", "MINIO_ROOT_PASSWORD"),
    )

    MLFLOW_S3_ENDPOINT_URL: str = "http://rustfs:9000"
    MLFLOW_TRACKING_URI: str = "http://mlflow:5000"

    MAX_DEPLOYMENTS_PER_PROJECT: int = 1

    TRAINING_IMAGE: str = "ghcr.io/codevisionx/covi-kitech-mlops-training:latest"
    SERVING_IMAGE: str = "ghcr.io/codevisionx/covi-kitech-mlops-base:latest"

    BUILDER_CPU_LIMIT: float = 4.0
    BUILDER_MEM_LIMIT: str = "4G"

    # 클래스 변수가 아닌 프로퍼티로 선언하여 최신 값을 반영하도록 함
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:5432/{self.POSTGRES_DB}"

    class Config:
        case_sensitive = True # 대소문자 구분

settings = Settings()