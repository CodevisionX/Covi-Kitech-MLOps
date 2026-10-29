from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class EvaluationParams(BaseModel):
    """검출 설정. 기본값은 고객 운영 코드(model_detection.py)와 같습니다."""
    conf: float = Field(0.25, gt=0, lt=1)
    iou: float = Field(0.3, gt=0, le=1)
    imgsz: int = Field(640, ge=32, le=4096)
    max_det: int = Field(20, ge=6, le=1000)
    padding: int = Field(0, ge=0, le=100)


class EvaluationCreate(BaseModel):
    project_id: int
    detection_job_id: int
    recognition_job_id: int
    dataset_version_id: int
    name: Optional[str] = Field(None, max_length=128)
    params: EvaluationParams = EvaluationParams()


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: Optional[str]
    detection_job_id: int
    recognition_job_id: int
    dataset_version_id: int
    params: Dict[str, Any]
    status: str
    status_message: Optional[str]
    error_message: Optional[str]
    run_id: Optional[str]
    experiment_id: Optional[str]
    metrics: Optional[Dict[str, Any]]
    summary: Optional[Dict[str, Any]]
    created_at: datetime
    finished_at: Optional[datetime]


class EvaluationReport(BaseModel):
    """[웹훅] 평가 컨테이너가 단계 결과를 보고합니다."""
    stage: str
    status: str                     # DONE | FAILED
    message: Optional[str] = None
    metrics: Optional[Dict[str, float]] = None
    summary: Optional[Dict[str, Any]] = None
