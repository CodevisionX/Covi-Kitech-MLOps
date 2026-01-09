from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.dependencies import get_db
from app.models.job import Job
from app.schemas.job import JobCreate, JobResponse, JobUpdateStatus
from app.services.job_service import JobService
from app.services.sse_service import sse_manager

router = APIRouter()

@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    job_in: JobCreate, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    """
    새로운 학습 작업을 생성하고 큐 처리를 시작합니다.
    1. DB에 PENDING 상태로 즉시 저장
    2. 사용자에게 201 응답 반환
    3. 백그라운드에서 MLflow 설정 및 컨테이너 가동 시작
    """
    service = JobService()

    # 1. DB 등록
    job = await service.register_job(job_in, db)
    # 2. 백그라운드 태스크 등록 (무거운 작업 분리)
    background_tasks.add_task(service.process_queue)
    
    return job

@router.get("/active", response_model=List[JobResponse])
def read_active_jobs(project_id: Optional[int] = None, db: Session = Depends(get_db)):
    """
    현재 대기 중(Pending)이거나 실행 중(Running)인 작업만 조회합니다.
    """
    service = JobService()
    return service.get_active_jobs(db, project_id=project_id)

# 학습 이력 리스트 (History 탭)
@router.get("/history", response_model=List[JobResponse])
def read_job_history(
    skip: int = 0, 
    limit: int = 20, 
    project_id: Optional[int] = None, # str -> int로 변경
    db: Session = Depends(get_db)
):
    """
    완료, 실패, 취소된 작업들의 이력을 페이징하여 조회하며 MLflow 지표를 포함합니다.
    """
    service = JobService()
    # 인자 이름(project_id)을 정확히 매칭하여 호출
    return service.get_job_history(db, project_id=project_id, skip=skip, limit=limit)

@router.get("/stream")
async def stream_events():
    """
    SSE 엔드포인트: 프론트엔드가 이 주소를 구독하여 실시간 업데이트를 받습니다.
    """
    return StreamingResponse(
        sse_manager.connect(), 
        media_type="text/event-stream"
    )

@router.get("/{job_id}", response_model=JobResponse)
def read_job(job_id: int, db: Session = Depends(get_db)):
    """
    특정 ID를 가진 작업의 상세 정보를 조회합니다.
    """
    service = JobService()
    job = service.get_job_by_id(db, job_id) 
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Job {job_id} not found"
        )
    return job

@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: int, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    """
    작업을 취소합니다. (Pending -> Canceled, Running -> Killed)
    """
    service = JobService()
    job = await service.cancel_job(db, job_id, background_tasks)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/{job_id}/complete")
async def complete_job(
    job_id: int, 
    status_update: JobUpdateStatus, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    """
    [Internal] 학습 컨테이너가 작업 완료/실패를 서버에 알리는 Webhook입니다.
    """
    service = JobService()
    # Enum.value를 사용하여 문자열로 변환 후 전달
    await service.complete_job(
        db,
        job_id, 
        status_update.status.value, 
        status_update.message, 
        background_tasks
    )
    return {"status": "ok"}

@router.get("/{job_id}/logs")
async def stream_logs(job_id: int):
    """
    작업 로그를 실시간으로 스트리밍합니다.
    - Running: Docker 컨테이너 로그
    - Finished/Failed: 저장된 로그 파일
    """
    service = JobService()
    return StreamingResponse(
        service.stream_job_logs(job_id),
        media_type="text/event-stream"
    )

@router.get("/{job_id}/logs/static")
async def read_static_logs(job_id: int, db: Session = Depends(get_db)):
    service = JobService()
    logs = await service.get_all_logs(db,job_id)
    return {"logs": logs}