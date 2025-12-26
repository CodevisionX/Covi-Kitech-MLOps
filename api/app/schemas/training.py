from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, validator

# 상태값 상수화
class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

# 공통 필드 정의
class TrainingJobBase(BaseModel):
    model_variant: str = Field(..., example="YOLOv8", description="학습할 모델의 종류")
    dataset: str = Field(..., example="pcb-dataset-v1", description="S3 버킷 또는 데이터셋 경로")
    epochs: int = Field(default=10, gt=0, description="학습 횟수 (0보다 커야 함)")
    batch: int = Field(default=16, gt=0, description="배치 사이즈 (0보다 커야 함)")

class TrainRequest(TrainingJobBase):
    @validator('model_variant')
    def validate_model_name(cls, v):
        allowed = ["YOLOv8", "EfficientNet"]
        if v not in allowed:
            raise ValueError(f"지원하지 않는 모델입니다. 허용 목록: {allowed}")
        return v

class TrainingJobUpdate(BaseModel):
    status: Optional[JobStatus] = None
    run_id: Optional[str] = None
    container_id: Optional[str] = None

class JobResponse(TrainingJobBase):
    id: int
    status: JobStatus
    run_id: Optional[str] = None
    container_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True