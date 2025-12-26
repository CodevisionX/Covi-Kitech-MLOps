from pydantic import BaseModel
from typing import List, Optional

class S3FileResponse(BaseModel):
    name: str
    full_path: str
    size: int

class BrowseResponse(BaseModel):
    current_path: str
    folders: List[str]
    files: List[S3FileResponse]

class DatasetListResponse(BaseModel):
    datasets: List[str]