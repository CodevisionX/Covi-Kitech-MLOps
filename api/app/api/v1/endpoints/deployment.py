import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.dependencies import get_db
from app.models.deployment import Deployment
from app.schemas.deployment import DeploymentCreate, DeploymentResponse
from app.services.deployment_service import deployment_service
from app.services.sse_service import sse_manager

router = APIRouter()

@router.post("/", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    deployment_in: DeploymentCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    1. 즉시 DB 레코드를 생성하고 (PENDING)
    2. 백그라운드 태스크를 등록한 뒤
    3. 201 응답을 즉시 반환합니다.
    """
    # 1. 초기 레코드 생성 및 자원 확인
    deployment = await deployment_service.prepare_deployment(
        db=db,
        project_id=deployment_in.project_id,
        model_name=deployment_in.model_name,
        run_id=deployment_in.run_id,
        model_version=deployment_in.model_version,
        job_id=deployment_in.job_id
    )

    # 2. 무거운 작업(MLflow 등록, 빌드 등)을 백그라운드로 던짐
    background_tasks.add_task(deployment_service._execute_deployment_flow, deployment.id)

    return deployment


@router.get("/active", response_model=List[DeploymentResponse])
def read_active_deployments(project_id: Optional[int] = None, db: Session = Depends(get_db)):
    """
    현재 실행 중(RUNNING)이거나 준비 중인 배포만 조회합니다.
    """
    query = db.query(Deployment).filter(
        Deployment.status.in_([
            "PENDING", "REGISTERING", "BUILDING", "CREATING", "RUNNING"
        ])
    )
    if project_id:
        query = query.filter(Deployment.project_id == project_id)
    return query.all()

@router.get("/{deployment_id}", response_model=DeploymentResponse)
def read_deployment(deployment_id: int, db: Session = Depends(get_db)):
    """
    특정 배포(Deployment)의 상세 정보를 조회합니다.
    """
    dep = db.query(Deployment).get(deployment_id)
    
    if not dep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Deployment with ID {deployment_id} not found"
        )
    
    return dep

@router.post("/{deployment_id}/stop", response_model=DeploymentResponse)
async def stop_deployment(
    deployment_id: int, 
    db: Session = Depends(get_db)
):
    """
    배포 중인 서비스를 중단하고 컨테이너를 삭제합니다.
    """
    await deployment_service.stop_deployment(deployment_id)
    
    return db.query(Deployment).get(deployment_id)

@router.delete("/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deployment(deployment_id: int):
    """문제가 있거나 불필요한 배포 이력을 DB에서 완전히 삭제합니다."""
    await deployment_service.delete_deployment(deployment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/{deployment_id}/logs")
def stream_deployment_logs(deployment_id: int, db: Session = Depends(get_db)):

    """
    BentoML 서빙 컨테이너의 로그를 실시간으로 스트리밍합니다.
    """
    from app.integrations.docker import docker_provider
    
    dep = db.query(Deployment).get(deployment_id)
    if not dep or not dep.container_id:
        raise HTTPException(status_code=404, detail="실행 중인 컨테이너를 찾을 수 없습니다.")
    
    return StreamingResponse(
        docker_provider.stream_container_logs(dep.container_id),
        media_type="text/event-stream"
    )

@router.post("/{deployment_id}/predict_visual")
async def predict_visual(
    deployment_id: int, 
    upload_file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    """
    [Proxy] 시각화된(Bounding Box가 그려진) 이미지를 반환합니다.
    Target BentoML: POST /predict_visual (BentoML 서비스 구현에 따라 경로 수정 필요)
    """
    # 1. 배포 정보 조회
    dep = db.query(Deployment).get(deployment_id)

    if not dep or not dep.container_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="배포 정보를 찾을 수 없거나 컨테이너가 실행 중이지 않습니다."
        )

    target_url = f"http://bento-serve-{deployment_id}:3000/predict_visual"
    
    try:
        async with httpx.AsyncClient() as client:
            file_content = await upload_file.read()

            files = {
                'image': (upload_file.filename, file_content, upload_file.content_type)
            }

            response = await client.post(target_url, files=files, timeout=10.0)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code, 
                    detail=f"모델 추론 컨테이너 오류: {response.text}"
                )
            
            return Response(content=response.content, media_type="image/jpeg")
        
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"BentoML 컨테이너 연결 실패: {str(exc)}"
        )
