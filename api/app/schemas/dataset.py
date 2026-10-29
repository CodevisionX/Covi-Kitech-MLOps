from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.constants import DatasetStatus, DatasetTask

NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"


class DatasetUploadCreate(BaseModel):
    project_id: int
    name: str = Field(pattern=NAME_PATTERN, description="영문/숫자/._- 만, 64자 이내")
    task: DatasetTask
    description: Optional[str] = None


class DatasetVersionResponse(BaseModel):
    id: int
    project_id: int
    name: str
    version: Optional[int] = None
    task: str
    description: Optional[str] = None
    status: DatasetStatus
    staging_prefix: str
    storage_path: Optional[str] = None
    data_path: Optional[str] = None
    manifest_sha256: Optional[str] = None
    file_count: Optional[int] = None
    total_bytes: Optional[int] = None
    stats: Optional[Dict[str, Any]] = None
    report: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    validated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        use_enum_values = True


class UploadSessionResponse(DatasetVersionResponse):
    """업로드 세션 생성 응답. CLI 로 올릴 때 쓸 S3 위치를 함께 알려 줍니다."""
    staging_uri: str
    s3_endpoint: str
    cli_example: str


class PresignFile(BaseModel):
    path: str = Field(min_length=1, max_length=1024, description="데이터셋 루트 기준 상대 경로")
    size: int = Field(ge=0)


class PresignRequest(BaseModel):
    files: List[PresignFile] = Field(min_length=1, max_length=1000)


class PresignedPart(BaseModel):
    part_number: int
    url: str


class PresignedFile(BaseModel):
    path: str
    method: str                       # PUT (한 번에) | MULTIPART (나눠서)
    url: Optional[str] = None
    upload_id: Optional[str] = None
    part_size: Optional[int] = None
    parts: Optional[List[PresignedPart]] = None


class PresignResponse(BaseModel):
    expires_in: int
    files: List[PresignedFile]


class CompletedPart(BaseModel):
    part_number: int = Field(ge=1, le=10000)
    etag: str


class MultipartComplete(BaseModel):
    path: str
    upload_id: str
    parts: List[CompletedPart] = Field(min_length=1)


class MultipartAbort(BaseModel):
    path: str
    upload_id: str


class ValidationResult(BaseModel):
    """검사 작업 컨테이너가 보내는 결과."""
    status: DatasetStatus
    message: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    report: Optional[Dict[str, Any]] = None
    manifest_sha256: Optional[str] = None
    file_count: Optional[int] = None
    total_bytes: Optional[int] = None
