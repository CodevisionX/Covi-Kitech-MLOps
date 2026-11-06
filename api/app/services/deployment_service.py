import logging
import asyncio
import httpx
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.deployment import Deployment
from app.core.constants import DeploymentStatus
from app.core.resource_manager import resource_manager
from app.services.sse_service import sse_manager
from app.integrations.mlflow import mlflow_provider
from app.integrations.docker import docker_provider
from app.core.config import settings
from app.models.job import Job
from app.core.constants import PYFUNC_SERVING_MODELS, is_pyfunc_job
from app.services.job_service import get_training_runtime

logger = logging.getLogger(__name__)

SERVING_PORT = 3000
SERVING_READY_TIMEOUT = 600  # 모델 다운로드 + 로드 대기 (초)


def serving_host(dep: Deployment) -> str:
    """mlops-net 안에서 서빙 컨테이너에 접속할 호스트 이름."""
    if dep.model_family in PYFUNC_SERVING_MODELS:
        return f"model-serve-{dep.id}"
    return f"bento-serve-{dep.id}"


class DeploymentService:

    async def prepare_deployment(self, db: Session, project_id: int, model_name: str, run_id: str, model_version: Optional[int], job_id: Optional[int]) -> Deployment:
        """빠르게 레코드만 생성하여 반환"""
        # 1. 자원 쿼터 확인
        if not resource_manager.check_project_quota(project_id):
            raise HTTPException(status_code=400, detail="배포 쿼터 초과")
        
        job = db.query(Job).get(job_id) if job_id is not None else None
        if job is None:
            job = db.query(Job).filter(Job.run_id == run_id).first()
            if job: job_id = job.id
        if job and job.run_id != run_id:
            raise HTTPException(status_code=400, detail="학습 작업과 run_id 가 맞지 않습니다")
        # 모델 종류: 학습 작업에서 확인. v1 방식 학습 기록은 이전처럼 이름으로 yolo/cnn 구분 (BentoML)
        if job and is_pyfunc_job(job):
            model_family = job.model_variant
        else:
            model_family = "yolo" if "yolo" in model_name.lower() else "cnn"

        # 2. PENDING 상태로 레코드 생성
        deployment = Deployment(
            project_id=project_id,
            job_id=job_id,
            model_name=model_name,
            model_version=model_version,
            run_id=run_id,
            model_family=model_family,
            status=DeploymentStatus.PENDING,
            status_message="배포 예약됨"
        )
        db.add(deployment)
        db.commit()
        db.refresh(deployment)
        return deployment

    async def _execute_deployment_flow(self, deployment_id: int):
        """
        실제 무거운 작업을 수행 (Background Task)
        실제 배포 공정 (MLflow 등록 -> 자원 할당 -> Docker 실행)
        [Flow] REGISTERING -> BUILDING -> CREATING -> RUNNING
        """
        print(f"[DeploymentFlow] Start flow for deployment_id: {deployment_id}")

        loop = asyncio.get_running_loop()

        async def update_status(status: DeploymentStatus, message: str, **kwargs):
            """DB 업데이트 및 SSE 알림 헬퍼"""
            print(f"[DeploymentFlow] Status Update: {status.value} - {message}")
            with SessionLocal() as db:
                dep = db.query(Deployment).get(deployment_id)
                if dep:
                    dep.status = status
                    dep.status_message = message
                    for key, value in kwargs.items(): setattr(dep, key, value)
                    db.commit()
                    await sse_manager.broadcast("deployment_status", {
                        "deployment_id": deployment_id,
                        "project_id": dep.project_id,
                        "status": status.value,
                        "message": message,
                        **kwargs
                    })

        try:
            # 1. REGISTERING: MLflow Model Registry에 정식 등록
            await update_status(DeploymentStatus.REGISTERING, "MLflow Model Registry에 모델을 등록 중입니다...")
            
            print(f"[DeploymentFlow] Fetching deployment object from DB...")
            dep_obj = None
            with SessionLocal() as db:
                dep_obj = db.query(Deployment).get(deployment_id)
                
            if not dep_obj:
                print(f"[DeploymentFlow] Error: Deployment object not found for id {deployment_id}")
                return

            print(f"[DeploymentFlow] Step 1: Registering model to MLflow (run_id: {dep_obj.run_id}, name: {dep_obj.model_name})")
            
            # MLflow Registry에 등록하고 버전 번호를 받아옵니다.
            new_version = await loop.run_in_executor(None, lambda: mlflow_provider.register_model(
                run_id=dep_obj.run_id, model_name=dep_obj.model_name
            ))
            print(f"[DeploymentFlow] Model registered successfully. New version: {new_version}")

            # DB에 새로 할당된 버전 정보 업데이트
            await update_status(
                DeploymentStatus.REGISTERING, 
                f"모델 등록 완료 (Version: {new_version})", 
                model_version=int(new_version)
            )

            if dep_obj.model_family in PYFUNC_SERVING_MODELS:
                await self._serve_pyfunc(deployment_id, dep_obj, new_version, update_status)
                return

            # 2. BUILDING: 별도의 컨테이너에게 일을 시킵니다.
            await update_status(DeploymentStatus.BUILDING, "빌드 전용 컨테이너를 가동합니다...")

            derived_model_type = dep_obj.model_family or (
                "yolo" if "yolo" in dep_obj.model_name.lower() else "cnn")

            # 빌더 컨테이너가 사용할 환경 변수 설정
            builder_env = {
                "MODEL_URI": f"models:/{dep_obj.model_name}/{new_version}",
                "MODEL_NAME": dep_obj.model_name,
                "DEPLOYMENT_ID": str(deployment_id),
                "MODEL_TYPE": derived_model_type,
                "MLFLOW_TRACKING_URI": settings.MLFLOW_TRACKING_URI,
                "MLFLOW_S3_ENDPOINT_URL": settings.MLFLOW_S3_ENDPOINT_URL,
                "AWS_ACCESS_KEY_ID": settings.S3_ACCESS_KEY,
                "AWS_SECRET_ACCESS_KEY": settings.S3_SECRET_KEY,
            }

            print(f"[DeploymentFlow] Dispatching builder for {dep_obj.model_name} as {derived_model_type}")
            print(f"[DeploymentFlow] Dispatching builder. Target MLflow: {settings.MLFLOW_TRACKING_URI}")            # 빌더 컨테이너 실행 및 완료 대기
            
            build_success = await loop.run_in_executor(None, lambda: docker_provider.run_builder_container(
                image=settings.BUILDER_IMAGE,
                name=f"bento-builder-{deployment_id}",
                environment=builder_env,
                volumes={settings.BENTOML_STORE_VOLUME: {"bind": "/root/.bentoml", "mode": "rw"}},
                network="mlops-net"
            ))

            if not build_success:
                raise Exception("빌드 컨테이너 작업이 실패했습니다. 로그를 확인하세요.")
            
            # --- STEP 3: CREATING (최종 Serving 컨테이너 가동) ---
            port = resource_manager.find_available_port()
            gpu_id = resource_manager.get_gpu_assignment()
            await update_status(DeploymentStatus.CREATING, "서빙 컨테이너를 생성 중입니다...", port=port)

            container = await loop.run_in_executor(
                None, 
                lambda: docker_provider.run_serving_container(
                    image=settings.SERVING_IMAGE,
                    name=f"bento-serve-{deployment_id}",
                    environment={
                        "BENTOML_MODEL_TAG": f"model_dep_{deployment_id}:latest",
                        "PORT": "3000"
                    },
                    port_mapping={3000: port},
                    network="mlops-net",
                    volumes={settings.BENTOML_STORE_VOLUME: {"bind": "/root/.bentoml", "mode": "rw"}},
                    gpu_id=gpu_id,
                )
            )

            # --- STEP 4: RUNNING ---
            endpoint_url = f"http://localhost:{port}"
            await update_status(DeploymentStatus.RUNNING, "서비스 가동 성공", container_id=container.id, endpoint_url=endpoint_url)

        except Exception as e:
            print(f"[DeploymentFlow] CRITICAL ERROR: {str(e)}")
            await update_status(DeploymentStatus.FAILED, "배포 실패", error_msg=str(e))

    async def _serve_pyfunc(self, deployment_id: int, dep_obj: Deployment, version, update_status):
        """YOLO26 / PP-OCRv6: 학습 이미지에서 등록된 모델을 MLflow 서빙으로 띄웁니다.

        학습 때와 같은 이미지(라이브러리 버전)로 추론하므로 별도 빌드가 필요 없습니다.
        API: POST /invocations (MLflow 표준), GET /ping
        """
        loop = asyncio.get_running_loop()
        image, _ = get_training_runtime(dep_obj.model_family)
        port = resource_manager.find_available_port()
        gpu_id = resource_manager.get_gpu_assignment()
        await update_status(DeploymentStatus.CREATING,
                            f"서빙 컨테이너를 시작합니다 ({'CPU' if gpu_id == 'cpu' else 'GPU'})", port=port)
        command = ["/app/.venv/bin/python", "-m", "mlflow", "models", "serve",
                   "-m", f"models:/{dep_obj.model_name}/{version}", "--env-manager", "local",
                   "-h", "0.0.0.0", "-p", str(SERVING_PORT), "-w", "1"]
        env = {
            "MLFLOW_TRACKING_URI": settings.MLFLOW_TRACKING_URI,
            "MLFLOW_S3_ENDPOINT_URL": settings.MLFLOW_S3_ENDPOINT_URL,
            "AWS_ACCESS_KEY_ID": settings.S3_ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": settings.S3_SECRET_KEY,
            "AWS_DEFAULT_REGION": "us-east-1",
            "MLFLOW_PYTHON_IGNORE_GIT_ERROR": "true",
            "PYTHONUNBUFFERED": "1",
        }
        if gpu_id == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = ""
        name = f"model-serve-{deployment_id}"
        try:
            container = await loop.run_in_executor(None, lambda: docker_provider.run_serving_container(
                image=image, name=name, environment=env,
                port_mapping={SERVING_PORT: port}, network="mlops-net", volumes={},
                gpu_id=gpu_id, command=command))
        except Exception:
            # 생성은 됐지만 시작에 실패한 컨테이너가 남지 않도록 정리
            try:
                docker_provider.get_container(name).remove(force=True)
            except Exception:
                pass
            raise
        await update_status(DeploymentStatus.CREATING, "모델을 내려받아 불러오는 중입니다...",
                            container_id=container.id)

        url = f"http://model-serve-{deployment_id}:{SERVING_PORT}/ping"
        async with httpx.AsyncClient() as client:
            for _ in range(SERVING_READY_TIMEOUT // 3):
                await asyncio.sleep(3)
                try:
                    if (await client.get(url, timeout=3)).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                container.reload()
                if container.status in ("exited", "dead") or container.attrs["RestartCount"] > 0:
                    tail = container.logs(tail=30).decode("utf-8", "replace")
                    container.remove(force=True)
                    raise RuntimeError(f"서빙 컨테이너가 시작되지 않았습니다:\n{tail}")
            else:
                raise RuntimeError(f"{SERVING_READY_TIMEOUT}초 안에 모델 서빙이 준비되지 않았습니다")
        await update_status(DeploymentStatus.RUNNING, "서비스 가동 성공",
                            endpoint_url=f"http://localhost:{port}/invocations")

    async def stop_deployment(self, deployment_id: int):
        """배포 중단 로직 (PENDING, RUNNING 모두 대응)"""
        with SessionLocal() as db:
            dep = db.query(Deployment).get(deployment_id)
            if not dep: return

            # 현재 상태에 따른 논리적 상태값 결정
            # 가동 중이면 STOPPED, 준비 중이면 CANCELED
            target_status = DeploymentStatus.STOPPED
            if dep.status in [DeploymentStatus.PENDING, DeploymentStatus.REGISTERING, DeploymentStatus.BUILDING, DeploymentStatus.CREATING]:
                target_status = DeploymentStatus.CANCELED
            
            # 1. 리소스 정리 (컨테이너 삭제)
            if dep.container_id:
                try:
                    container = docker_provider.get_container(dep.container_id)
                    container.remove(force=True)
                except: pass
            
            # 2. DB 업데이트
            dep.status = target_status
            dep.status_message = "사용자 요청에 의해 중단되었습니다."
            db.commit()

            # 3. SSE 알림
            await sse_manager.broadcast("deployment_status", {
                "deployment_id": deployment_id,
                "project_id": dep.project_id,
                "status": target_status.value,
                "message": dep.status_message
            })

    async def delete_deployment(self, deployment_id: int):
        """배포 이력 완전 삭제 (DB에서 제거)"""
        with SessionLocal() as db:
            dep = db.query(Deployment).get(deployment_id)
            if not dep: return

            # 컨테이너가 있다면 삭제
            if dep.container_id:
                try:
                    container = docker_provider.get_container(dep.container_id)
                    container.remove(force=True)
                except: pass

            db.delete(dep)
            db.commit()

            # SSE로 삭제 알림 (id만 전달하여 목록에서 제거 유도)
            await sse_manager.broadcast("deployment_status", {
                "deployment_id": deployment_id,
                "status": "DELETED"
            })

deployment_service = DeploymentService()
