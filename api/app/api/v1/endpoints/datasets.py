# 데이터셋 업로드 / 검사 / 등록된 버전 조회
from typing import List, Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.schemas.dataset import (DatasetUploadCreate, DatasetVersionResponse, MultipartAbort,
                                 MultipartComplete, PresignRequest, PresignResponse,
                                 UploadSessionResponse, ValidationResult)
from app.services.dataset_service import dataset_service

router = APIRouter()


def _with_upload_info(dv, request: Request) -> UploadSessionResponse:
    base = DatasetVersionResponse.model_validate(dv).model_dump()
    return UploadSessionResponse(**base, **dataset_service.upload_info(dv, request.url.hostname))


@router.post("/uploads", response_model=UploadSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_upload(body: DatasetUploadCreate, request: Request, db: Session = Depends(get_db)):
    """업로드 세션을 만들고 임시 영역 위치(CLI 업로드용 포함)를 돌려줍니다."""
    dv = await dataset_service.create_upload(db, body)
    return _with_upload_info(dv, request)


@router.get("/uploads/{version_id}", response_model=UploadSessionResponse)
def get_upload(version_id: int, request: Request, db: Session = Depends(get_db)):
    return _with_upload_info(dataset_service.get(db, version_id), request)


@router.post("/uploads/{version_id}/presign", response_model=PresignResponse)
def presign(version_id: int, body: PresignRequest, request: Request, db: Session = Depends(get_db)):
    """파일별 업로드 URL. 큰 파일은 조각별 URL(MULTIPART)을 줍니다. 한 번에 최대 1000개."""
    dv = dataset_service.get(db, version_id)
    return dataset_service.presign(dv, body, request.url.hostname)


@router.post("/uploads/{version_id}/multipart/complete", status_code=status.HTTP_204_NO_CONTENT)
def complete_multipart(version_id: int, body: MultipartComplete, db: Session = Depends(get_db)):
    dataset_service.complete_multipart(dataset_service.get(db, version_id), body)


@router.post("/uploads/{version_id}/multipart/abort", status_code=status.HTTP_204_NO_CONTENT)
def abort_multipart(version_id: int, body: MultipartAbort, db: Session = Depends(get_db)):
    dataset_service.abort_multipart(dataset_service.get(db, version_id), body)


@router.get("/uploads/{version_id}/summary")
def staging_summary(version_id: int, db: Session = Depends(get_db)):
    """임시 영역에 지금까지 올라간 파일 수와 크기."""
    return dataset_service.staging_summary(dataset_service.get(db, version_id))


@router.post("/uploads/{version_id}/validate", response_model=DatasetVersionResponse)
async def validate(version_id: int, db: Session = Depends(get_db)):
    """올린 파일을 검사해 새 버전으로 등록합니다. 실패한 업로드는 고친 뒤 다시 호출할 수 있습니다."""
    return await dataset_service.start_validation(db, dataset_service.get(db, version_id))


@router.get("/versions", response_model=List[DatasetVersionResponse])
def list_versions(project_id: Optional[int] = None, name: Optional[str] = None,
                  task: Optional[str] = None, status: Optional[str] = None,
                  db: Session = Depends(get_db)):
    return dataset_service.list(db, project_id, name, task, status)


@router.get("/versions/{version_id}", response_model=DatasetVersionResponse)
def get_version(version_id: int, db: Session = Depends(get_db)):
    return dataset_service.get(db, version_id)


@router.get("/versions/{version_id}/logs", response_class=PlainTextResponse)
def get_logs(version_id: int, db: Session = Depends(get_db)):
    return dataset_service.read_log(dataset_service.get(db, version_id))


@router.delete("/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(version_id: int, db: Session = Depends(get_db)):
    """업로드 중/실패한 세션, 또는 어떤 학습에도 쓰이지 않은 등록 버전을 지웁니다."""
    await dataset_service.delete(db, dataset_service.get(db, version_id))


@router.post("/versions/{version_id}/complete", include_in_schema=False)
async def complete_validation(version_id: int, body: ValidationResult, db: Session = Depends(get_db)):
    """[웹훅] 검사 컨테이너가 결과를 보고합니다."""
    dv = await dataset_service.complete_validation(db, dataset_service.get(db, version_id), body)
    return {"status": dv.status}
