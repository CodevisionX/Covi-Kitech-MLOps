from pydantic import BaseModel
from typing import List, Dict, Optional

class ExperimentResponse(BaseModel):
    experiment_id: str
    name: str
    lifecycle_stage: str

class RunResponse(BaseModel):
    run_id: str
    run_name: str
    status: str
    start_time: int
    metrics: Dict[str, float]
    params: Dict[str, str]   