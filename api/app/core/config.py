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

    # 데이터셋 업로드: 브라우저가 RustFS 로 직접 올리므로 브라우저에서 닿는 주소가 필요합니다.
    # 비우면 접속한 주소의 호스트 + S3_PUBLIC_PORT 를 씁니다 (예: http://10.0.0.5:9000).
    DATASET_BUCKET_NAME: str = "datasets"
    S3_PUBLIC_ENDPOINT_URL: str = ""
    S3_PUBLIC_PORT: int = Field(9000, validation_alias=AliasChoices("S3_PUBLIC_PORT", "S3_PORT"))
    # 데이터셋 버킷 CORS 허용 Origin (쉼표 구분). 업로드 URL 은 서명돼 있어 * 여도 키 없이는 못 씁니다.
    S3_CORS_ALLOWED_ORIGINS: str = "*"
    UPLOAD_URL_EXPIRES: int = 6 * 3600
    UPLOAD_SINGLE_PUT_MAX: int = 64 * 1024 * 1024   # 이보다 큰 파일은 나눠 올리기(multipart)
    UPLOAD_PART_SIZE: int = 64 * 1024 * 1024
    MLFLOW_TRACKING_URI: str = "http://mlflow:5000"

    MAX_DEPLOYMENTS_PER_PROJECT: int = 2  # 검출 + 인식 모델을 함께 띄워 확인할 수 있도록

    TRAINING_IMAGE: str = "ghcr.io/codevisionx/covi-kitech-mlops-training:latest"
    # 신규 모델 학습 이미지 (검출: YOLO26, 인식: PP-OCRv6)
    TRAINING_IMAGE_YOLO26: str = "ghcr.io/codevisionx/covi-kitech-mlops-training-yolo26:latest"
    TRAINING_IMAGE_PPOCR: str = "ghcr.io/codevisionx/covi-kitech-mlops-training-ppocr:latest"
    SERVING_IMAGE: str = "ghcr.io/codevisionx/covi-kitech-mlops-base:latest"
    BUILDER_IMAGE: str = "ghcr.io/codevisionx/covi-kitech-mlops-builder:latest"

    # 백엔드가 직접 띄우는 학습/빌더/서빙 컨테이너에 붙일 볼륨 이름.
    # docker-compose 의 volumes.*.name 과 같아야 합니다.
    TRAINING_RESULTS_VOLUME: str = "mlops_kitech_training_results"
    BENTOML_STORE_VOLUME: str = "mlops_bentoml_model_store"

    BUILDER_CPU_LIMIT: float = 4.0
    BUILDER_MEM_LIMIT: str = "4G"

    # 클래스 변수가 아닌 프로퍼티로 선언하여 최신 값을 반영하도록 함
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:5432/{self.POSTGRES_DB}"

    class Config:
        case_sensitive = True # 대소문자 구분

settings = Settings()