from pydantic import BaseModel
from typing import List, Dict, Optional

class ExperimentResponse(BaseModel):
    experiment_id: str
    name: str
    lifecycle_stage: str

class RunResponse(BaseModel):
    run_id: str
    run_name: Optional[str] = None
    status: str
    start_time: int
    end_time: Optional[int] = None
    metrics: Dict[str, float]
    params: Dict[str, str]
    tags: Dict[str, str]  # MLflow에 저장된 태그
    artifact_uri: Optional[str] = None