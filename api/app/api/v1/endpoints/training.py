# 학습 시작, 취소, 상태 조회
import asyncio
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from app.db.dependencies import get_db

from app.schemas.training import TrainRequest, JobResponse, JobStatus
from app.services.TrainingService import training_service
from app.models.training import TrainingJob
from app.integrations.docker import docker_provider
import docker
import json
import os

router = APIRouter()

@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def start_training(
    req: TrainRequest, 
    db: Session = Depends(get_db)
):
    """
    새로운 학습 작업을 생성하고 큐에 대기시킵니다.
    """
    return await training_service.enqueue_job(db, req)

@router.get("/active", response_model=List[JobResponse])
async def get_active_jobs(db: Session = Depends(get_db)):
    """
    현재 진행 중이거나 대기 중인 작업 목록을 조회합니다.
    """
    jobs = db.query(TrainingJob).filter(
        TrainingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
    ).all()
    return jobs

@router.get("/history", response_model=List[JobResponse])
async def get_job_history(db: Session = Depends(get_db)):
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
    db: Session = Depends(get_db)
):
    """
    진행 중인 작업을 취소합니다. (도커 중지 및 상태 업데이트)
    """
    job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    
    if job.status in [JobStatus.FINISHED, JobStatus.FAILED, JobStatus.CANCELLED]:
        return {"message": f"Job {job_id}는 이미 {job.status} 상태입니다."}
    
    try:
        if job.container_id:
            try:
                container = docker_provider.get_container(job.container_id)
                container.stop(timeout=2)
                print(f"Container {job.container_id} stopped successfully.")
            except docker.errors.NotFound:
                print(f"Container {job.container_id} not found on host.")
            except Exception as e:
                print(f"Docker stop error: {str(e)}")
        
        await training_service.update_job_status(db, job_id, JobStatus.CANCELLED)

        return {
            "status": "success",
            "message": f"Job {job_id} 가 취소되었습니다.",
            "job_id": job_id
        }
    
    except Exception as e:
        db.rollback() # 오류 발생 시 DB 롤백
        raise HTTPException(status_code=500, detail=f"취소 처리 중 오류: {str(e)}")

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
                    log_line = line.decode('utf-8').strip()
                    yield f"data: {json.dumps({'message': log_line})}\n\n"
            except docker.errors.NotFound:
                # 2. 컨테이너가 없으면 저장된 로그 파일 확인
                if os.path.exists(log_file_path):
                    with open(log_file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            yield f"data: {json.dumps({'message': line.strip()})}\n\n"
                else:
                    error_data = {"error": "로그 파일을 찾을 수 없습니다."}
                    yield f"data: {json.dumps(error_data)}\n\n"
        except Exception as e:
            error_data = {"error": f"Unexpected error: {str(e)}"}
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(generate_logs(), media_type="text/event-stream")
    