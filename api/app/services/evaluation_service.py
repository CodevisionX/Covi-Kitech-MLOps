# E2E 평가 (검출 + 인식) 실행과 배포 패키지 생성
import asyncio
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import mlflow
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import DatasetStatus, DatasetTask, EvaluationStatus, JobStatus
from app.db.session import SessionLocal
from app.integrations.docker import docker_provider
from app.integrations.mlflow import mlflow_provider
from app.models.dataset import DatasetVersion
from app.models.evaluation import Evaluation
from app.models.job import Job, get_kst_now
from app.models.project import Project
from app.schemas.evaluation import EvaluationCreate, EvaluationReport
from app.services.sse_service import sse_manager

LOG_DIR = "/app/runs/evaluations"

# 단계별 실행 이미지. 각 모델을 학습한 것과 같은 환경에서 추론합니다.
STAGES = (
    ("detect", EvaluationStatus.DETECTING, lambda: settings.TRAINING_IMAGE_YOLO26),
    ("recognize", EvaluationStatus.RECOGNIZING, lambda: settings.TRAINING_IMAGE_PPOCR),
)

# 고객 현장 폴더 구조: (모델 아티팩트 안에서 찾을 파일 이름, 패키지 안 경로)
# 학습 결과가 last.pt 로 대체됐더라도 현장 규칙에 맞춰 best.pt 로 넣습니다.
PACKAGE_FILES = {
    "detection": [("*.pt", "models/detection/best.pt")],
    "recognition": [(f"inference.{ext}", f"models/recognition/inference.{ext}")
                    for ext in ("json", "pdiparams", "yml")],
}
# 학습 때 기록한 model_sha256 이 가리키는 파일 (패키지 파일이 학습 결과와 같은지 확인)
TRAINED_HASH_FILE = {"detection": "models/detection/best.pt",
                     "recognition": "models/recognition/inference.pdiparams"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


class EvaluationService:

    # ------------------------------------------------------------ 생성
    def _finished_job(self, db: Session, job_id: int, variant: str, project_id: int) -> Job:
        job = db.query(Job).get(job_id)
        if not job:
            raise HTTPException(404, f"학습 작업 {job_id} 이 없습니다")
        if job.model_variant != variant:
            raise HTTPException(400, f"학습 작업 {job_id} 은 {variant} 모델이 아닙니다 ({job.model_variant})")
        if job.project_id != project_id:
            raise HTTPException(400, f"학습 작업 {job_id} 은 다른 프로젝트의 작업입니다")
        if job.status != JobStatus.FINISHED.value or not job.run_id:
            raise HTTPException(400, f"학습 작업 {job_id} 이 완료되지 않았습니다 ({job.status})")
        return job

    async def create(self, db: Session, body: EvaluationCreate) -> Evaluation:
        project = db.query(Project).get(body.project_id)
        if not project:
            raise HTTPException(404, "프로젝트가 없습니다")
        det = self._finished_job(db, body.detection_job_id, "YOLO26", project.id)
        rec = self._finished_job(db, body.recognition_job_id, "PP-OCRv6", project.id)
        dv = db.query(DatasetVersion).get(body.dataset_version_id)
        if not dv or dv.project_id != project.id:
            raise HTTPException(400, "이 프로젝트의 데이터셋 버전이 아닙니다")
        if dv.status != DatasetStatus.READY.value or dv.task != DatasetTask.E2E.value:
            raise HTTPException(400, f"E2E 평가에는 등록 완료(READY)된 e2e 데이터셋이 필요합니다 "
                                     f"({dv.name} v{dv.version}: {dv.task}, {dv.status})")
        # 학습에 쓴 데이터로 평가하면 점수가 부풀려지므로 알림만 남김 (막지는 않음)
        overlap = [j.id for j in (det, rec) if j.dataset_version_id == dv.id]

        ev = Evaluation(project_id=project.id, name=body.name, detection_job_id=det.id,
                        recognition_job_id=rec.id, dataset_version_id=dv.id,
                        params=body.params.model_dump(), status=EvaluationStatus.PENDING.value,
                        status_message="평가 대기", metrics={}, summary={})
        db.add(ev)
        db.commit()

        loop = asyncio.get_running_loop()
        try:
            run = await loop.run_in_executor(None, lambda: mlflow_provider.create_run(
                experiment_name=f"{project.name}_E2E"))
            tags = {
                "project_name": project.name, "task": "e2e_evaluation", "evaluation_id": str(ev.id),
                "detection_job_id": str(det.id), "detection_run_id": det.run_id,
                "recognition_job_id": str(rec.id), "recognition_run_id": rec.run_id,
                "dataset_version": f"{dv.name}:v{dv.version}", "dataset_sha256": dv.manifest_sha256 or "",
                "mlflow.runName": body.name or f"e2e-{ev.id}",
            }
            await loop.run_in_executor(None, lambda: [
                mlflow_provider.client.set_tag(run.info.run_id, k, v) for k, v in tags.items()])
        except Exception as e:
            ev.status = EvaluationStatus.FAILED.value
            ev.error_message = f"MLflow run 생성 실패: {e}"
            db.commit()
            raise HTTPException(500, ev.error_message)
        ev.run_id, ev.experiment_id = run.info.run_id, run.info.experiment_id
        if overlap:
            ev.status_message = f"주의: 학습 작업 {overlap} 이 같은 데이터셋으로 학습했습니다"
        db.commit()
        db.refresh(ev)
        asyncio.create_task(self._run(ev.id))
        return ev

    # ------------------------------------------------------------ 실행
    def _env(self, ev: Evaluation, stage: str) -> dict:
        dv = ev.dataset_version
        env = {
            "STAGE": stage,
            "EVALUATION_ID": str(ev.id),
            "MLFLOW_RUN_ID": ev.run_id,
            "MLFLOW_TRACKING_URI": settings.MLFLOW_TRACKING_URI,
            "MLFLOW_S3_ENDPOINT_URL": settings.MLFLOW_S3_ENDPOINT_URL,
            "AWS_ACCESS_KEY_ID": settings.S3_ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": settings.S3_SECRET_KEY,
            "AWS_DEFAULT_REGION": "us-east-1",
            "BACKEND_URL": "http://backend:8000",
            "DATASET_PATH": dv.data_path,
            "DATASET_MANIFEST_SHA256": dv.manifest_sha256 or "",
            "DETECTION_RUN_ID": ev.detection_job.run_id,
            "RECOGNITION_RUN_ID": ev.recognition_job.run_id,
            "PYTHONUNBUFFERED": "1",
            "MLFLOW_PYTHON_IGNORE_GIT_ERROR": "true",
        }
        env.update({k.upper(): str(v) for k, v in (ev.params or {}).items()})
        return env

    async def _set(self, ev_id: int, **fields) -> Evaluation:
        with SessionLocal() as db:
            ev = db.query(Evaluation).get(ev_id)
            for k, v in fields.items():
                setattr(ev, k, v)
            db.commit()
            db.refresh(ev)
            await sse_manager.broadcast("evaluation_status", {
                "id": ev.id, "project_id": ev.project_id, "status": ev.status,
                "message": ev.status_message})
            return ev

    async def _run(self, ev_id: int):
        loop = asyncio.get_running_loop()
        for stage, status, image in STAGES:
            with SessionLocal() as db:
                ev = db.query(Evaluation).get(ev_id)
                if ev.status == EvaluationStatus.FAILED.value:
                    return
                env = self._env(ev, stage)
            await self._set(ev_id, status=status.value, status_message=f"{stage} 단계 실행 중")
            command = ["/bin/bash", "-o", "pipefail", "-c",
                       f"mkdir -p {LOG_DIR} && /app/.venv/bin/python -u evaluate_e2e.py 2>&1 "
                       f"| tee -a {LOG_DIR}/{ev_id}.log"]
            try:
                container = await loop.run_in_executor(None, lambda: docker_provider.run_container(
                    image=image(), command=command, environment=env, network="mlops-net",
                    volumes={settings.TRAINING_RESULTS_VOLUME: {"bind": "/app/runs", "mode": "rw"}},
                    detach=True))
                await self._set(ev_id, container_id=container.id)
                result = await loop.run_in_executor(None, container.wait)
                code = result.get("StatusCode", 1)
                await loop.run_in_executor(None, lambda: container.remove(force=True))
            except Exception as e:
                code = f"컨테이너 오류: {e}"
            if code != 0:
                return await self._fail(ev_id, f"{stage} 단계 실패 (exit {code})")

        with SessionLocal() as db:
            ev = db.query(Evaluation).get(ev_id)
            ok, run_id = bool(ev.metrics), ev.run_id
        if not ok:
            return await self._fail(ev_id, "평가 결과 보고 없이 종료되었습니다")
        await loop.run_in_executor(None, lambda: mlflow_provider.update_run_status(run_id, "FINISHED"))
        await self._set(ev_id, status=EvaluationStatus.FINISHED.value, container_id=None,
                        status_message="평가 완료", finished_at=get_kst_now())

    async def _fail(self, ev_id: int, message: str):
        with SessionLocal() as db:
            ev = db.query(Evaluation).get(ev_id)
            # 컨테이너가 보낸 상세 오류가 있으면 그것을 유지
            error = ev.error_message or message
            run_id = ev.run_id
        try:
            mlflow_provider.update_run_status(run_id, "FAILED")
        except Exception:
            pass
        await self._set(ev_id, status=EvaluationStatus.FAILED.value, error_message=error,
                        status_message=message, container_id=None, finished_at=get_kst_now())

    async def report(self, db: Session, ev: Evaluation, body: EvaluationReport):
        if body.status == "FAILED":
            ev.error_message = body.message
        elif body.stage == "recognize":
            ev.metrics = body.metrics or {}
            ev.summary = body.summary or {}
        ev.status_message = body.message or ev.status_message
        db.commit()

    # ------------------------------------------------------------ 조회 / 삭제
    def get(self, db: Session, ev_id: int) -> Evaluation:
        ev = db.query(Evaluation).get(ev_id)
        if not ev:
            raise HTTPException(404, "평가가 없습니다")
        return ev

    def list(self, db: Session, project_id=None):
        q = db.query(Evaluation)
        if project_id is not None:
            q = q.filter(Evaluation.project_id == project_id)
        return q.order_by(Evaluation.id.desc()).all()

    def read_log(self, ev: Evaluation) -> str:
        path = os.path.join(LOG_DIR, f"{ev.id}.log")
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()

    def predictions_csv(self, ev: Evaluation) -> str:
        if ev.status != EvaluationStatus.FINISHED.value:
            raise HTTPException(409, "평가가 끝나지 않았습니다")
        with tempfile.TemporaryDirectory() as tmp:
            path = mlflow.artifacts.download_artifacts(run_id=ev.run_id, artifact_path="e2e/predictions.csv",
                                                       dst_path=tmp)
            return Path(path).read_text(encoding="utf-8")

    async def delete(self, db: Session, ev: Evaluation):
        if ev.status in (EvaluationStatus.PENDING.value, EvaluationStatus.DETECTING.value,
                         EvaluationStatus.RECOGNIZING.value):
            if ev.container_id:
                try:
                    docker_provider.get_container(ev.container_id).remove(force=True)
                except Exception:
                    pass
            try:
                mlflow_provider.update_run_status(ev.run_id, "KILLED")
            except Exception:
                pass
        # MLflow run 은 기록으로 남김
        db.delete(ev)
        db.commit()
        await sse_manager.broadcast("evaluation_status", {"id": ev.id, "project_id": ev.project_id,
                                                          "status": "DELETED"})

    # ------------------------------------------------------------ 배포 패키지
    def build_package(self, db: Session, ev: Evaluation) -> Path:
        """E2E 평가를 마친 모델 조합을 고객 현장 폴더 구조의 zip 으로 만듭니다.

        models/detection/best.pt
        models/recognition/inference.json / inference.pdiparams / inference.yml
        package_info.json   모델 출처(학습 run, 데이터셋 버전), 파일 해시, E2E 지표, 추론 설정
        """
        if ev.status != EvaluationStatus.FINISHED.value:
            raise HTTPException(409, "E2E 평가를 마친 조합만 배포 패키지로 만들 수 있습니다")
        tmp = Path(tempfile.mkdtemp(prefix="pkg_"))
        try:
            stage = tmp / "package"
            info = {"format": 1, "created_at": get_kst_now().isoformat(), "models": {}, "files": {}}
            client = mlflow_provider.client
            for role, job in (("detection", ev.detection_job), ("recognition", ev.recognition_job)):
                src = Path(mlflow.artifacts.download_artifacts(artifact_uri=f"runs:/{job.run_id}/model",
                                                               dst_path=str(tmp / role)))
                for pattern, rel_dst in PACKAGE_FILES[role]:
                    found = sorted((src / "artifacts").rglob(pattern))
                    if len(found) != 1:
                        raise HTTPException(500, f"{role} 모델에서 {pattern} 파일을 하나로 특정할 수 없습니다 "
                                                 f"({len(found)}개, 학습 작업 {job.id})")
                    (stage / rel_dst).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(found[0], stage / rel_dst)
                    info["files"][rel_dst] = {"sha256": _sha256(stage / rel_dst),
                                              "size": (stage / rel_dst).stat().st_size}
                run = client.get_run(job.run_id)
                trained = run.data.params.get("model_sha256")
                packed = info["files"][TRAINED_HASH_FILE[role]]["sha256"]
                if trained and trained != packed:
                    raise HTTPException(500, f"{role} 모델 파일이 학습 기록과 다릅니다 "
                                             f"(기록 {trained[:12]}, 실제 {packed[:12]})")
                dv = job.dataset_version_id and db.query(DatasetVersion).get(job.dataset_version_id)
                info["models"][role] = {
                    "model": job.model_variant, "job_id": job.id, "run_id": job.run_id,
                    "dataset_version": f"{dv.name}:v{dv.version}" if dv else None,
                    "dataset_sha256": dv.manifest_sha256 if dv else None,
                    "best_val": {k: v for k, v in run.data.metrics.items() if k.startswith("best_val/")},
                    "test": {k: v for k, v in run.data.metrics.items() if k.startswith("test/")},
                }
            edv = ev.dataset_version
            info["evaluation"] = {
                "id": ev.id, "run_id": ev.run_id, "metrics": ev.metrics,
                "dataset_version": f"{edv.name}:v{edv.version}", "dataset_sha256": edv.manifest_sha256,
            }
            p = ev.params or {}
            info["inference_settings"] = {
                "detection": {"imgsz": p.get("imgsz"), "conf": p.get("conf"), "iou": p.get("iou"),
                              "max_det": p.get("max_det"), "end2end": False, "padding": p.get("padding"),
                              "expected_boxes_per_panel": 6},
                "slot_order": "중심 x 로 2개씩 열을 나누고 열 안에서 위->아래 (1,2 / 3,4 / 5,6)",
            }
            (stage / "package_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                                     encoding="utf-8")
            out = tmp / "package.zip"
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(stage.rglob("*")):
                    if f.is_file():
                        zf.write(f, f.relative_to(stage).as_posix())
            return out
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise


evaluation_service = EvaluationService()
