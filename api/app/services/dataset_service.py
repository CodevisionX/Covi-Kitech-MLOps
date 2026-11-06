"""데이터셋 업로드 / 검사 / 버전 등록.

1. 업로드 세션 생성: DB 에 UPLOADING 행, 임시 영역 datasets/_staging/<uuid>/ 할당
2. 파일 올리기: 브라우저는 서명 URL 로 RustFS 에 직접(큰 파일은 나눠서),
   대용량은 CLI(aws s3 sync, rclone)나 RustFS 콘솔로 같은 임시 영역에 올림
3. 검사 시작: 버전 번호 부여 -> 작업 종류의 학습 이미지로 검사 컨테이너 실행(GPU 없음)
4. 검사 결과: 통과하면 registered/... 에 매니페스트와 함께 저장되고 READY (이후 변경 불가)
"""
import asyncio
import os
import posixpath
import uuid
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import DatasetStatus, DatasetTask
from app.db.session import SessionLocal
from app.integrations.docker import docker_provider
from app.integrations.s3 import s3_provider
from app.models.dataset import DatasetVersion
from app.models.job import Job, get_kst_now
from app.models.project import Project
from app.schemas.dataset import (DatasetUploadCreate, MultipartAbort, MultipartComplete,
                                 PresignRequest, ValidationResult)
from app.services.sse_service import sse_manager

LOG_DIR = "/app/runs/datasets"


def clean_relative_path(path: str) -> str:
    """브라우저가 보낸 상대 경로를 정리하고, 임시 영역 밖을 가리키는 경로는 거부합니다."""
    p = path.replace("\\", "/").lstrip("/")
    parts = p.split("/")
    if not p or any(seg in ("", ".", "..") for seg in parts):
        raise HTTPException(400, f"잘못된 파일 경로입니다: {path!r}")
    return posixpath.join(*parts)


def public_endpoint(request_host: Optional[str], scheme: str = "http") -> str:
    if settings.S3_PUBLIC_ENDPOINT_URL:
        return settings.S3_PUBLIC_ENDPOINT_URL.rstrip("/")
    host = request_host or "localhost"
    return f"{scheme}://{host}:{settings.S3_PUBLIC_PORT}"


def training_image_for(task: str) -> str:
    return {
        DatasetTask.DETECTION.value: settings.TRAINING_IMAGE_YOLO26,
        DatasetTask.RECOGNITION.value: settings.TRAINING_IMAGE_PPOCR,
        DatasetTask.E2E.value: settings.TRAINING_IMAGE_PPOCR,  # 정답 문자를 인식 사전과 대조
        DatasetTask.TIMESERIES.value: settings.TRAINING_IMAGE_YOLO26,  # numpy 만 필요 (1D-CNN 학습 이미지)
    }[task]


class DatasetService:
    bucket = property(lambda self: settings.DATASET_BUCKET_NAME)

    # ---------------------------------------------------------------- 조회
    def get(self, db: Session, version_id: int) -> DatasetVersion:
        dv = db.query(DatasetVersion).filter(DatasetVersion.id == version_id).first()
        if not dv:
            raise HTTPException(404, "데이터셋 버전을 찾을 수 없습니다")
        return dv

    def list(self, db: Session, project_id: Optional[int] = None, name: Optional[str] = None,
             task: Optional[str] = None, status: Optional[str] = None) -> List[DatasetVersion]:
        q = db.query(DatasetVersion)
        if project_id is not None:
            q = q.filter(DatasetVersion.project_id == project_id)
        if name:
            q = q.filter(DatasetVersion.name == name)
        if task:
            q = q.filter(DatasetVersion.task == task)
        if status:
            q = q.filter(DatasetVersion.status == status)
        return q.order_by(DatasetVersion.name.asc(), DatasetVersion.version.desc().nullsfirst(),
                          DatasetVersion.id.desc()).all()

    # ---------------------------------------------------------------- 업로드
    async def create_upload(self, db: Session, data: DatasetUploadCreate) -> DatasetVersion:
        if not db.query(Project).filter(Project.id == data.project_id).first():
            raise HTTPException(404, "프로젝트를 찾을 수 없습니다")
        same_name = db.query(DatasetVersion).filter(
            DatasetVersion.project_id == data.project_id, DatasetVersion.name == data.name,
            DatasetVersion.status == DatasetStatus.READY.value).first()
        if same_name and same_name.task != data.task.value:
            raise HTTPException(409, f"'{data.name}' 은(는) 이미 {same_name.task} 데이터셋 이름입니다")
        dv = DatasetVersion(
            project_id=data.project_id, name=data.name, task=data.task.value,
            description=data.description, status=DatasetStatus.UPLOADING.value,
            staging_prefix=f"_staging/{uuid.uuid4().hex}/",
        )
        db.add(dv)
        db.commit()
        db.refresh(dv)
        await self._notify(dv)
        return dv

    def upload_info(self, dv: DatasetVersion, request_host: Optional[str]) -> dict:
        endpoint = public_endpoint(request_host)
        uri = f"s3://{self.bucket}/{dv.staging_prefix}"
        return {
            "staging_uri": uri,
            "s3_endpoint": endpoint,
            "cli_example": f"aws s3 sync ./<데이터셋 폴더> {uri} --endpoint-url {endpoint}",
        }

    def _require_uploading(self, dv: DatasetVersion):
        if dv.status not in (DatasetStatus.UPLOADING.value, DatasetStatus.FAILED.value):
            raise HTTPException(409, f"업로드할 수 없는 상태입니다: {dv.status}")

    def presign(self, dv: DatasetVersion, req: PresignRequest, request_host: Optional[str]) -> dict:
        self._require_uploading(dv)
        endpoint = public_endpoint(request_host)
        expires = settings.UPLOAD_URL_EXPIRES
        out = []
        for f in req.files:
            rel = clean_relative_path(f.path)
            key = dv.staging_prefix + rel
            if f.size <= settings.UPLOAD_SINGLE_PUT_MAX:
                out.append({"path": rel, "method": "PUT",
                            "url": s3_provider.presign_put(endpoint, self.bucket, key, expires)})
            else:
                upload_id, part_size, parts = s3_provider.start_multipart(
                    endpoint, self.bucket, key, f.size, expires)
                out.append({"path": rel, "method": "MULTIPART", "upload_id": upload_id,
                            "part_size": part_size, "parts": parts})
        return {"expires_in": expires, "files": out}

    def complete_multipart(self, dv: DatasetVersion, body: MultipartComplete):
        self._require_uploading(dv)
        key = dv.staging_prefix + clean_relative_path(body.path)
        try:
            s3_provider.complete_multipart(self.bucket, key, body.upload_id, body.parts)
        except Exception as e:
            raise HTTPException(400, f"나눠 올리기 완료 실패: {e}")

    def abort_multipart(self, dv: DatasetVersion, body: MultipartAbort):
        key = dv.staging_prefix + clean_relative_path(body.path)
        try:
            s3_provider.abort_multipart(self.bucket, key, body.upload_id)
        except Exception as e:
            raise HTTPException(400, f"나눠 올리기 취소 실패: {e}")

    def staging_summary(self, dv: DatasetVersion) -> dict:
        count, size = s3_provider.prefix_summary(self.bucket, dv.staging_prefix)
        return {"file_count": count, "total_bytes": size}

    # ---------------------------------------------------------------- 검사
    async def start_validation(self, db: Session, dv: DatasetVersion) -> DatasetVersion:
        self._require_uploading(dv)
        count, _ = s3_provider.prefix_summary(self.bucket, dv.staging_prefix)
        if count == 0:
            raise HTTPException(400, "임시 영역에 올린 파일이 없습니다")

        # 버전 번호 부여 (같은 이름 안에서 1, 2, 3 ...). 동시에 요청돼도 UNIQUE 제약으로 한쪽만 성공
        for _ in range(3):
            latest = db.query(func.max(DatasetVersion.version)).filter(
                DatasetVersion.project_id == dv.project_id, DatasetVersion.name == dv.name).scalar()
            dv.version = (latest or 0) + 1
            dv.storage_path = f"{self.bucket}/registered/p{dv.project_id}/{dv.name}/v{dv.version}"
            dv.status = DatasetStatus.VALIDATING.value
            dv.error_message, dv.report, dv.stats = None, {}, {}
            try:
                db.commit()
                break
            except IntegrityError:
                db.rollback()
        else:
            raise HTTPException(409, "버전 번호를 정하지 못했습니다. 다시 시도하세요")

        env = {
            "DATASET_VERSION_ID": str(dv.id),
            "DATASET_TASK": dv.task,
            "STAGING_PATH": f"{self.bucket}/{dv.staging_prefix}",
            "TARGET_PATH": dv.storage_path,
            "BACKEND_URL": "http://backend:8000",
            "MLFLOW_S3_ENDPOINT_URL": settings.MLFLOW_S3_ENDPOINT_URL,
            "AWS_ACCESS_KEY_ID": settings.S3_ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": settings.S3_SECRET_KEY,
            "AWS_DEFAULT_REGION": "us-east-1",
            "PYTHONUNBUFFERED": "1",
        }
        command = ["/bin/bash", "-o", "pipefail", "-c",
                   f"mkdir -p {LOG_DIR} && /app/.venv/bin/python -u validate_dataset.py 2>&1 "
                   f"| tee {LOG_DIR}/{dv.id}.log"]
        loop = asyncio.get_running_loop()
        try:
            container = await loop.run_in_executor(None, lambda: docker_provider.run_container(
                image=training_image_for(dv.task), command=command, environment=env,
                network="mlops-net",
                volumes={settings.TRAINING_RESULTS_VOLUME: {"bind": "/app/runs", "mode": "rw"}},
                detach=True, gpu=False))
        except Exception as e:
            self._mark_failed(dv, f"검사 컨테이너 실행 실패: {e}")
            db.commit()
            await self._notify(dv)
            raise HTTPException(500, dv.error_message)
        dv.container_id = container.id
        db.commit()
        db.refresh(dv)
        await self._notify(dv)
        asyncio.create_task(self._watch(dv.id, container))
        return dv

    def _mark_failed(self, dv: DatasetVersion, message: str):
        dv.status = DatasetStatus.FAILED.value
        dv.error_message = message
        dv.version = None          # 실패한 버전은 번호를 쓰지 않음
        dv.storage_path = None

    async def _watch(self, version_id: int, container):
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, container.wait)
            code = result.get("StatusCode", 1)
        except Exception as e:
            code = str(e)
        with SessionLocal() as db:
            dv = db.query(DatasetVersion).filter(DatasetVersion.id == version_id).first()
            if dv and dv.status == DatasetStatus.VALIDATING.value:
                # 웹훅 없이 끝났다면(강제 종료, 메모리 부족 등) 실패로 정리
                self._mark_failed(dv, f"검사 작업이 결과 보고 없이 종료되었습니다 (exit {code})")
                dv.container_id = None
                db.commit()
                await self._notify(dv)
        try:
            await loop.run_in_executor(None, lambda: container.remove(force=True))
        except Exception:
            pass

    async def complete_validation(self, db: Session, dv: DatasetVersion, result: ValidationResult):
        if dv.status != DatasetStatus.VALIDATING.value:
            return dv  # 중복/늦은 보고 무시
        dv.stats = result.stats or {}
        dv.report = result.report or {}
        if result.status == DatasetStatus.READY:
            dv.status = DatasetStatus.READY.value
            dv.manifest_sha256 = result.manifest_sha256
            dv.file_count = result.file_count
            dv.total_bytes = result.total_bytes
            dv.validated_at = get_kst_now()
            dv.error_message = None
        else:
            self._mark_failed(dv, result.message or "검사 실패")
        db.commit()
        db.refresh(dv)
        await self._notify(dv)
        return dv

    # ---------------------------------------------------------------- 삭제
    async def delete(self, db: Session, dv: DatasetVersion):
        if dv.status == DatasetStatus.VALIDATING.value:
            raise HTTPException(409, "검사 중에는 삭제할 수 없습니다")
        if dv.status == DatasetStatus.READY.value:
            used = db.query(Job).filter(Job.dataset_version_id == dv.id).count()
            if used:
                raise HTTPException(409, f"학습 작업 {used}건이 이 버전을 사용해 삭제할 수 없습니다")
            from app.models.evaluation import Evaluation
            used = db.query(Evaluation).filter(Evaluation.dataset_version_id == dv.id).count()
            if used:
                raise HTTPException(409, f"E2E 평가 {used}건이 이 버전을 사용해 삭제할 수 없습니다")
            s3_provider.delete_prefix(self.bucket, dv.storage_path.split("/", 1)[1] + "/")
        s3_provider.delete_prefix(self.bucket, dv.staging_prefix)
        db.delete(dv)
        db.commit()
        await sse_manager.broadcast("dataset_status", {"id": dv.id, "status": "DELETED",
                                                       "project_id": dv.project_id})

    def read_log(self, dv: DatasetVersion) -> str:
        path = os.path.join(LOG_DIR, f"{dv.id}.log")
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()

    async def _notify(self, dv: DatasetVersion):
        await sse_manager.broadcast("dataset_status", {
            "id": dv.id, "status": dv.status, "project_id": dv.project_id,
            "name": dv.name, "version": dv.version,
        })


dataset_service = DatasetService()
