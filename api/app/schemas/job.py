from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
from app.core.constants import JobStatus
from app.schemas.deployment import DeploymentSimple

class JobBase(BaseModel):
    project_id: int
    experiment_id: Optional[str] = "0"
    model_variant: str
    # 기존 모델(YOLOv8, 1D-CNN)은 버킷 경로를 직접 지정, 신규 모델은 dataset_version_id 로 지정
    dataset: str = ""
    dataset_version_id: Optional[int] = None
    # 파라미터는 키-값이 무엇이든 올 수 있게 Dict[str, Any]로 정의
    params: Dict[str, Any] = Field(default_factory=lambda: {"epochs": 10, "batch": 16})
    tags: Dict[str, Any] = Field(default_factory=dict)

class JobCreate(JobBase):
    pass

class JobUpdateStatus(BaseModel):
    status: JobStatus 
    message: Optional[str] = None

    # 들어오는 status 값을 자동으로 대문자로 변환해주는 검증기 추가
    @field_validator('status', mode='before')
    @classmethod
    def to_upper(cls, v):
        if isinstance(v, str):
            return v.upper()
        return v

class JobResponse(JobBase):
    id: int
    status: JobStatus
    created_at: datetime
    updated_at: Optional[datetime]
    finished_at: Optional[datetime]
    started_at: Optional[datetime] = None
    run_id: Optional[str] = None
    container_id: Optional[str] = None
    deployment: Optional[DeploymentSimple] = None
    error_message: Optional[str] = None
    metrics: Optional[Dict[str, float]] = None
    # 실행 중인 학습의 에폭 진행도 {"epoch": 완료 에폭, "total": 전체 에폭} (MLflow 기록 기준)
    progress: Optional[Dict[str, int]] = None
    
    class Config:
        from_attributes = True
        use_enum_values = True