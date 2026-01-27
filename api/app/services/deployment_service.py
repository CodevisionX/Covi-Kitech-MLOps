import logging
import asyncio
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

logger = logging.getLogger(__name__)

class DeploymentService:

    async def prepare_deployment(self, db: Session, project_id: int, model_name: str, run_id: str, model_version: Optional[int], job_id: Optional[int]) -> Deployment:
        """빠르게 레코드만 생성하여 반환"""
        # 1. 자원 쿼터 확인
        if not resource_manager.check_project_quota(project_id):
            raise HTTPException(status_code=400, detail="배포 쿼터 초과")
        
        if job_id is None:
            existing_job = db.query(Job).filter(Job.run_id == run_id).first()
            if existing_job: job_id = existing_job.id

        # 2. PENDING 상태로 레코드 생성
        deployment = Deployment(
            project_id=project_id,
            job_id=job_id,
            model_name=model_name,
            model_version=model_version,
            run_id=run_id,
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

            # 2. BUILDING: 별도의 컨테이너에게 일을 시킵니다.
            await update_status(DeploymentStatus.BUILDING, "빌드 전용 컨테이너를 가동합니다...")

            model_name_lower = dep_obj.model_name.lower()
            derived_model_type = "yolo" if "yolo" in model_name_lower else "cnn"

            # 빌더 컨테이너가 사용할 환경 변수 설정
            builder_env = {
                "MODEL_URI": f"models:/{dep_obj.model_name}/{new_version}",
                "MODEL_NAME": dep_obj.model_name,
                "DEPLOYMENT_ID": str(deployment_id),
                "MODEL_TYPE": derived_model_type,
                "MLFLOW_TRACKING_URI": settings.MLFLOW_TRACKING_URI,
                "MLFLOW_S3_ENDPOINT_URL": settings.MLFLOW_S3_ENDPOINT_URL,
                "AWS_ACCESS_KEY_ID": settings.MINIO_ROOT_USER,
                "AWS_SECRET_ACCESS_KEY": settings.MINIO_ROOT_PASSWORD,
            }

            print(f"[DeploymentFlow] Dispatching builder for {dep_obj.model_name} as {derived_model_type}")
            print(f"[DeploymentFlow] Dispatching builder. Target MLflow: {settings.MLFLOW_TRACKING_URI}")            # 빌더 컨테이너 실행 및 완료 대기
            
            build_success = await loop.run_in_executor(None, lambda: docker_provider.run_builder_container(
                image="ghcr.io/codevisionx/covi-kitech-mlops-builder:latest", # "mlops-builder:latest",
                name=f"bento-builder-{deployment_id}",
                environment=builder_env,
                volumes={"bentoml_model_store": {"bind": "/root/.bentoml", "mode": "rw"}},
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
                    volumes={"bentoml_model_store": {"bind": "/root/.bentoml", "mode": "rw"}},
                    gpu_id=gpu_id,
                )
            )

            # --- STEP 4: RUNNING ---
            endpoint_url = f"http://localhost:{port}"
            await update_status(DeploymentStatus.RUNNING, "서비스 가동 성공", container_id=container.id, endpoint_url=endpoint_url)

        except Exception as e:
            print(f"[DeploymentFlow] CRITICAL ERROR: {str(e)}")
            await update_status(DeploymentStatus.FAILED, "배포 실패", error_msg=str(e))

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
