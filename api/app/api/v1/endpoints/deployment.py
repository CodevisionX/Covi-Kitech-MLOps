from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.dependencies import get_db
from app.schemas.deployment import DeploymentCreate, DeploymentResponse
from app.services.deployment_service import deployment_service
from app.services.sse_service import sse_manager

router = APIRouter()

@router.post("/", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    deployment_in: DeploymentCreate, 
    db: Session = Depends(get_db)
):
    """
    새로운 모델 배포 요청을 생성하고 배포 파이프라인(MLflow->BentoML->Docker)을 시작합니다.
    """
    # deployment_service 내에서 비동기 태스크(asyncio.create_task)가 실행됩니다.
    service_instance = deployment_service
    service_instance.db = db # DB 세션 주입
    return await service_instance.deploy_model(
        project_id=deployment_in.project_id,
        model_name=deployment_in.model_name,
        model_version=deployment_in.model_version,
        run_id=deployment_in.run_id,
        job_id=deployment_in.job_id
    )


@router.get("/active", response_model=List[DeploymentResponse])
def read_active_deployments(project_id: Optional[int] = None, db: Session = Depends(get_db)):
    """
    현재 실행 중(RUNNING)이거나 준비 중인 배포만 조회합니다.
    """
    from app.models.deployment import Deployment
    query = db.query(Deployment).filter(
        Deployment.status.in_([
            "PENDING", "REGISTERING", "BUILDING", "CREATING", "RUNNING"
        ])
    )
    if project_id:
        query = query.filter(Deployment.project_id == project_id)
    return query.all()

@router.post("/{deployment_id}/stop", response_model=DeploymentResponse)
async def stop_deployment(
    deployment_id: int, 
    db: Session = Depends(get_db)
):
    """
    배포 중인 서비스를 중단하고 컨테이너를 삭제합니다.
    """
    service_instance = deployment_service
    service_instance.db = db
    await service_instance.stop_deployment(deployment_id)
    
    from app.models.deployment import Deployment
    return db.query(Deployment).get(deployment_id)

@router.get("/{deployment_id}/logs")
async def stream_deployment_logs(deployment_id: int, db: Session = Depends(get_db)):
    """
    BentoML 서빙 컨테이너의 로그를 실시간으로 스트리밍합니다.
    """
    from app.integrations.docker import docker_provider
    from app.models.deployment import Deployment
    
    dep = db.query(Deployment).get(deployment_id)
    if not dep or not dep.container_id:
        raise HTTPException(status_code=404, detail="실행 중인 컨테이너를 찾을 수 없습니다.")
    
    return StreamingResponse(
        docker_provider.stream_container_logs(dep.container_id),
        media_type="text/event-stream"
    )
