# 큐 관리, 작업 상태 전파 (SSE), 학습 엔진 호출을 조율import asyncio
import asyncio
import datetime
import json
import traceback
from sqlalchemy.orm import Session
from app.models.training import TrainingJob
from app.schemas.training import TrainRequest, JobStatus
from app.integrations.docker import docker_provider
from app.integrations.mlflow import mlflow_provider
from app.db.session import SessionLocal
from app.core.config import settings

class TrainingService:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.subscribers = []
    
    async def update_job_status(self, db: Session, job_id: int, status: str, event: str = "status_changed"):
        """
        DB 상태를 업데이트하고 모든 구독자에게 SSE 알림을 보냅니다.
        """
        job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
        if job:
            if status == JobStatus.CANCELLED and job.run_id:
                try:
                    mlflow_provider.update_run_status(job.run_id, "KILLED")
                except Exception as e:
                    print(f"MLflow status update error: {e}")

            job.status = status
            job.updated_at = datetime.datetime.now()
            db.commit()
            
            # SSE 전파 (이미 만들어두신 broadcast 활용)
            self.broadcast({
                "job_id": job_id,
                "status": status,
                "event": event,
                "message": f"작업 #{job_id}의 상태가 {status}(으)로 변경되었습니다."
            })
            return job
        return None
    
    async def enqueue_job(self, db: Session, req: TrainRequest):
        new_job = TrainingJob(
            model_variant=req.model_variant,
            dataset=req.dataset,
            epochs=req.epochs,
            batch=req.batch,
            status=JobStatus.PENDING
        )
        db.add(new_job)
        db.commit()
        db.refresh(new_job)

        await self.queue.put({"job_id": new_job.id})
        self.broadcast({"job_id": new_job.id, "status": JobStatus.PENDING, "event": "job_queued"})
        return new_job

    async def run_worker(self):
        print("Training Worker 시작: 대기열 감시 중...")
        while True:
            job_info = await self.queue.get()
            job_id = job_info["job_id"]
            
            with SessionLocal() as db:
                try:
                    await self._process_job(db, job_id)
                except Exception as e:
                    print(f"Job {job_id} 처리 중 에러: {e}")
                    traceback.print_print_exc()
                finally:
                    self.queue.task_done()
                
    async def _process_job(self, db: Session, job_id: int):
        job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
        if not job or job.status == JobStatus.CANCELLED:
            return

        await self.update_job_status(db, job_id, JobStatus.RUNNING)

        run = mlflow_provider.create_run(f"{job.model_variant}_Experiments")
        job.run_id = run.info.run_id
        db.commit()

        # 2. 도커 실행
        env_vars = {
            "MLFLOW_RUN_ID": job.run_id,
            "MLFLOW_TRACKING_URI": settings.MLFLOW_TRACKING_URI,
            "MLFLOW_S3_ENDPOINT_URL": settings.MLFLOW_S3_ENDPOINT_URL,
            "AWS_ACCESS_KEY_ID": settings.MINIO_ROOT_USER,
            "AWS_SECRET_ACCESS_KEY": settings.MINIO_ROOT_PASSWORD,
            "DATASET_PATH": job.dataset,
            "EPOCHS": str(job.epochs),
            "BATCH": str(job.batch),
        }

        train_script = "train_yolo.py" if job.model_variant == "YOLOv8" else "train_effnet.py"
        command = f"python {train_script}"

        container = docker_provider.run_container(
            image="mlops_kitech-training",
            command=command,
            environment=env_vars,
            volumes={'training_logs': {'bind': '/app/runs', 'mode': 'rw'}},
            network="mlops-net"
        )

        job.container_id = container.id
        db.commit()

        self.broadcast({
            "event": "container_created", 
            "job_id": job_id, 
            "container_id": container.id
        })

        # 3. 비동기로 상태 모니터링 시작
        await self._watch_status(job_id, job.run_id)
    
    async def _watch_status(self, job_id: int, run_id: str):
        print(f"Job {job_id} 모니터링 시작 (MLflow Run: {run_id})")

        while True:
            await asyncio.sleep(5)
            try:
                run = mlflow_provider.get_run(run_id)
                status = run.info.status # FINISHED, FAILED 등

                if status not in ["RUNNING", "SCHEDULED"]:
                    with SessionLocal() as db:
                        await self.update_job_status(db, job_id, status)
                
                    print(f"Job {job_id} 종료 감지: {status}")
                    break
            except Exception as e:
                print(f"Job {job_id} 모니터링 중 오류: {e}")
                await asyncio.sleep(10)

    def broadcast(self, message: dict):
        data = f"data: {json.dumps(message)}\n\n"
        for q in self.subscribers:
            q.put_nowait(data)

training_service = TrainingService()