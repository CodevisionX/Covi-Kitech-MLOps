from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
from app.core.constants import JobStatus

class JobBase(BaseModel):
    project_id: int
    experiment_id: Optional[str] = "0"
    model_variant: str
    dataset: str
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
    run_id: Optional[str] = None
    container_id: Optional[str] = None
    error_message: Optional[str] = None
    metrics: Optional[Dict[str, float]] = None
    
    class Config:
        from_attributes = True
        use_enum_values = True