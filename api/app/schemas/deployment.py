from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
from app.core.constants import DeploymentStatus

class DeploymentBase(BaseModel):
    project_id: int
    model_name: str
    model_version: Optional[int] = None
    run_id: str
    job_id: Optional[int] = None

class DeploymentCreate(DeploymentBase):
    """배포 생성 요청 시 사용하는 스키마"""
    pass

class DeploymentUpdateStatus(BaseModel):
    """배포 상태 업데이트용 (내부 서비스용)"""
    status: DeploymentStatus
    message: Optional[str] = None

    @field_validator('status', mode='before')
    @classmethod
    def to_upper(cls, v):
        if isinstance(v, str):
            return v.upper()
        return v

class DeploymentSimple(BaseModel):
    id: int
    status: str
    endpoint_url: Optional[str]
    port: Optional[int]

    class Config:
        from_attributes = True

class DeploymentResponse(DeploymentBase):
    """API 응답 시 사용하는 스키마"""
    id: int
    status: DeploymentStatus
    status_message: Optional[str] = None
    container_id: Optional[str] = None
    port: Optional[int] = None
    endpoint_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
        use_enum_values = True