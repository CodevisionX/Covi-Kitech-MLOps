# 학습 시작, 취소, 상태 조회
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List

from app.api import deps
from app.schemas.training import TrainRequest, JobResponse, JobStatus
from app.services.training_service import training_service
from app.models.training import TrainingJob
from app.integrations.docker import docker_provider
import docker

router = APIRouter()

@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def start_training(
    req: TrainRequest, 
    db: Session = Depends(deps.get_db)
):
    """
    새로운 학습 작업을 생성하고 큐에 대기시킵니다.
    """
    return await training_service.enqueue_job(db, req)

@router.get("/active", response_model=List[JobResponse])
async def get_active_jobs(db: Session = Depends(deps.get_db)):
    """
    현재 진행 중이거나 대기 중인 작업 목록을 조회합니다.
    """
    jobs = db.query(TrainingJob).filter(
        TrainingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
    ).all()
    return jobs

@router.get("/history", response_model=List[JobResponse])
async def get_job_history(db: Session = Depends(deps.get_db)):
    """
    완료, 실패 또는 취소된 작업 이력을 조회합니다.
    """
    jobs = db.query(TrainingJob).filter(
        TrainingJob.status.in_([JobStatus.FINISHED, JobStatus.FAILED, JobStatus.CANCELLED])
    ).order_by(TrainingJob.created_at.desc()).all()
    return jobs

@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: int, 
    db: Session = Depends(deps.get_db)
):
    """
    진행 중인 작업을 취소합니다. (도커 중지 및 상태 업데이트)
    """
    # 실제 취소 로직은 서비스 레이어에 위임하는 것이 좋습니다.
    # 여기서는 간단히 상태 확인 및 서비스 호출 예시만 작성합니다.
    job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    
    # service.cancel_job(job_id) 형태의 메서드를 추가하여 호출 가능
    return {"message": f"Job {job_id} 취소 요청이 접수되었습니다."}

@router.get("/status-stream")
async def status_stream():
    """
    학습 상태 변경 사항을 실시간으로 스트리밍합니다. (SSE)
    """
    async def event_generator():
        queue = asyncio.Queue()
        training_service.subscribers.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            training_service.subscribers.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/{container_id}/logs")
async def stream_logs(container_id: str):
    """
    컨테이너의 실시간 로그를 SSE로 스트리밍합니다.
    컨테이너가 종료된 경우 저장된 파일 로그를 읽어옵니다.
    """
    log_file_path = f"/app/runs/{container_id[:12]}.log"

    def generate_logs():
        try:
            try:
                # 1. 활성 컨테이너에서 로그 스트리밍 시도
                container = docker_provider.get_container(container_id)
                for line in container.logs(stream=True, follow=True, tail=100):
                    yield f"data: {line.decode('utf-8')}\n\n"
            except docker.errors.NotFound:
                # 2. 컨테이너가 없으면 저장된 로그 파일 확인
                if os.path.exists(log_file_path):
                    with open(log_file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            yield f"data: {line}\n\n"
                else:
                    yield f"data: Error: 로그 파일을 찾을 수 없습니다.\n\n"
        except Exception as e:
            yield f"data: Unexpected error: {str(e)}\n\n"

    return StreamingResponse(generate_logs(), media_type="text/event-stream")
    