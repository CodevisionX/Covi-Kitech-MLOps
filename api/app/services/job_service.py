import os
import asyncio
import json
from typing import List, Any, Optional, Dict
import docker
from app.db.session import SessionLocal
from sqlalchemy.orm import Session
from fastapi import BackgroundTasks
from datetime import datetime
import aiofiles

# Models & Schemas
from app.models.job import Job, get_kst_now
from app.models.project import Project
from app.schemas.job import JobCreate
from app.core.constants import JobStatus

# Integrations
from app.integrations.docker import docker_provider
from app.integrations.mlflow import mlflow_provider
from app.core.config import settings

# Services
from app.services.sse_service import sse_manager

class JobService:
    def __init__(self, db: Session = None):
        self.db = db
        self.log_dir = "/app/runs"
    
    async def create_job(self, job_in: JobCreate, background_tasks: BackgroundTasks):
        """
        사용자 요청 -> DB 저장(Pending) -> 큐 프로세스 트리거
        """
        job = Job(
            project_id=job_in.project_id,
            experiment_id=job_in.experiment_id or "0",
            dataset=job_in.dataset,
            model_variant=job_in.model_variant,
            params=job_in.params,
            tags=job_in.tags,
            status=JobStatus.PENDING.value
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        # 1. 프론트에 "새 작업 등록됨" 알림
        await sse_manager.broadcast("new_job", {
            "job_id": job.id, 
            "status": job.status,
            "project_id": job.project_id 
        })

        # 2. 백그라운드에서 큐 처리 시작 (Trigger Next)
        background_tasks.add_task(self.process_queue)
        return job
    
    async def process_queue(self):
        """
        [안정성 강화] 직접 세션을 관리하여 세션 만료를 방지하고, 중복 실행을 막음
        """
        # 1. 백그라운드 실행을 위해 새로운 세션 생성 (Context Manager 사용)
        with SessionLocal() as db:
            try:
                # 2. 중복 실행 방지 로직 (Critical Section)
                # 현재 'RUNNING' 상태인 작업이 하나라도 있으면 즉시 종료
                running_job = db.query(Job).filter(Job.status == JobStatus.RUNNING.value).first()
                if running_job:
                    print(f"[JobService] Job {running_job.id} is already running. Skipping...")
                    return

                # 3. 대기 중(PENDING)인 가장 오래된 작업 조회
                next_job = db.query(Job).filter(
                    Job.status == JobStatus.PENDING.value
                ).order_by(Job.id.asc()).first()

                if not next_job:
                    print("[JobService] No pending jobs in queue.")
                    return

                # 4. 작업 시작 처리 (세션을 인자로 넘겨줌)
                print(f"[JobService] Picking next job ID: {next_job.id}")
                await self._start_job_execution(next_job, db)
                
            except Exception as e:
                print(f"[Queue Error] Error in process_queue: {e}")
                db.rollback()
    
    async def _start_job_execution(self, job: Job, db: Session):
        """
        실제 Docker 컨테이너 실행 및 상태 업데이트
        """
        try:
            
            project = db.query(Project).filter(Project.id == job.project_id).first()
            project_name = project.name if project else "Default"
            experiment_name = f"{project_name}_{job.model_variant}"

            print(f"[JobService] Starting Job ID: {job.id}")
            # 상태 변경: Pending -> Running
            job.status = JobStatus.RUNNING.value

            # MLflow Run 생성
            run = mlflow_provider.create_run(experiment_name=experiment_name)
            job.run_id = run.info.run_id
            job.experiment_id = run.info.experiment_id

            mlflow_provider.client.set_tag(job.run_id, "project_name", project_name)
            mlflow_provider.client.set_tag(job.run_id, "model_variant", job.model_variant)

            if job.tags:
                for key, value in job.tags.items():
                    mlflow_provider.client.set_tag(job.run_id, key, value)
            
            db.commit()

            # SSE 알림
            await sse_manager.broadcast("status_change", {
                "job_id": job.id, 
                "status": JobStatus.RUNNING.value,
                "project_id": job.project_id
            })

            # Docker 실행 환경변수 구성
            env_vars = {
                "MLFLOW_RUN_ID": job.run_id,
                "MLFLOW_TRACKING_URI": settings.MLFLOW_TRACKING_URI,
                "MLFLOW_S3_ENDPOINT_URL": settings.MLFLOW_S3_ENDPOINT_URL,
                "AWS_ACCESS_KEY_ID": settings.MINIO_ROOT_USER,
                "AWS_SECRET_ACCESS_KEY": settings.MINIO_ROOT_PASSWORD,
                "DATASET_PATH": job.dataset,
                "JOB_ID": str(job.id),
                "BACKEND_URL": "http://backend:8000",
                "JOB_TAGS": json.dumps(job.tags)
            }

            # JSON 파라미터를 환경변수로 변환 (예: {"epochs": 10} -> EPOCHS=10)
            if job.params:
                for k, v in job.params.items():
                    env_vars[k.upper()] = str(v)
            
            train_script = "train_yolo.py" if job.model_variant == "YOLOv8" else "train_effnet.py"
            log_file = f"/app/runs/{job.id}.log"

            # -u 옵션과 tee 명령어를 더 확실하게 전달
            command = [
                "sh", "-c", 
                f"python -u {train_script} 2>&1 | tee {log_file}"
            ]

            # 컨테이너 실행
            container = docker_provider.run_container(
                image="mlops_kitech-training",
                command=command,
                environment=env_vars,
                network="mlops-net",
                volumes={
                    'mlops_kitech_training_results': {'bind': '/app/runs', 'mode': 'rw'}
                },
                detach=True
            )

            job.container_id = container.id
            db.commit()
            asyncio.create_task(self._monitor_container_completion(job.id, container))
        except Exception as e:
            print(f"[Critical Error] Job {job.id} failed: {e}")
            job.status = JobStatus.FAILED.value
            job.error_message = str(e)
            db.commit()
            await sse_manager.broadcast("status_change", {
                "job_id": job.id, 
                "status": "FAILED",
                "project_id": job.project_id
            })
            await self._safe_retry_queue()
    
    async def _monitor_container_completion(self, job_id: int, container):
        try:
            # 1. 컨테이너가 멈출 때까지 기다림 (Blocking 연산이므로 쓰레드 풀에서 실행)
            loop = asyncio.get_running_loop()
            # container.wait()는 컨테이너가 종료될 때까지 대기하는 Docker SDK 함수
            result = await loop.run_in_executor(None, container.wait)

            # 2. 종료 코드 확인 (0이면 성공, 아니면 실패)
            exit_code = result.get('StatusCode', 1)
            final_status = JobStatus.FINISHED.value if exit_code == 0 else JobStatus.FAILED.value
            
            # 3. DB 세션이 만료되었을 수 있으므로 새로 생성하거나 처리해야 함
            with SessionLocal() as db:
                await self._handle_job_completion(job_id, final_status, exit_code, db)
        except Exception as e:
            with SessionLocal() as db:
                await self._handle_job_completion(job_id, JobStatus.FAILED.value, str(e), db)
    
    async def _handle_job_completion(self, job_id: int, status_str: str, exit_info: any, db: Session):
        job = db.query(Job).filter(Job.id == job_id).first()
        if job and job.status == JobStatus.RUNNING.value:
            job.status = status_str
            job.finished_at = get_kst_now()
            if status_str == JobStatus.FAILED.value:
                job.error_message = f"Exit Code: {exit_info}"
            
            if job.container_id:
                try:
                    container = docker_provider.get_container(job.container_id)
                    container.remove(force=True)
                except: pass
                job.container_id = None
            
            db.commit()

            await sse_manager.broadcast("status_change", {
                "job_id": job.id, 
                "status": status_str,
                "project_id": job.project_id
            })
            print(f"[JobService] Job {job_id} finished. Triggering next...")
            await self.process_queue()

    async def _safe_retry_queue(self):
        """실패 시 잠시 대기 후 다음 큐 실행 (무한 루프 폭주 방지)"""
        await asyncio.sleep(2) 
        await self.process_queue()
    
    async def cancel_job(self, job_id: int, background_tasks: BackgroundTasks):
        """
        작업 취소 로직
        """
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return None
        
        previous_status = job.status
        # 1. PENDING 상태 취소
        if job.status == JobStatus.PENDING.value:
            job.status = JobStatus.CANCELED.value
            job.finished_at = get_kst_now()
            self.db.commit()

        # 2. RUNNING 상태 취소 (Docker Kill)
        elif job.status == JobStatus.RUNNING.value:
            if job.container_id:
                try:
                    container = docker_provider.get_container(job.container_id)
                    container.kill()
                    print(f"Container {job.container_id} killed.")

                    container.remove(force=True)
                    print(f"Container {job.container_id} removed.")

                except Exception as e:
                    print(f"Error killing container: {e}")
            
            job.status = JobStatus.KILLED.value
            job.finished_at = get_kst_now()
            job.container_id = None
            
            # MLflow 상태 업데이트
            if job.run_id:
                try:
                    mlflow_provider.update_run_status(job.run_id, "KILLED")
                except: pass
            self.db.commit()

            # 실행 중인 작업이 죽었으므로, 대기 중인 다음 작업 트리거
            background_tasks.add_task(self.process_queue)
        
        # 상태 변경 알림
        if previous_status != job.status:
            await sse_manager.broadcast("status_change", {
                "job_id": job.id, 
                "status": job.status,
                "project_id": job.project_id
            })
        return job

    async def complete_job(self, job_id: int, status_str: str, message: str, background_tasks: BackgroundTasks):
        """
        [Webhook Handler] 학습 컨테이너가 종료될 때 호출됨
        """
        job = self.db.query(Job).filter(Job.id == job_id).first()

        # 이미 취소되었거나 완료된 작업 무시 (중복 호출 방지)
        if job and job.status == JobStatus.RUNNING.value:
            s_upper = status_str.upper()
            final_status = JobStatus.FINISHED.value if s_upper == "FINISHED" else JobStatus.FAILED.value
            job.status = final_status
            job.error_message = message
            job.finished_at = get_kst_now()
            
            if job.container_id:
                try:
                    container = docker_provider.get_container(job.container_id)
                    container.remove(force=True)
                    print(f"Container {job.container_id} removed.")
                except Exception as e:
                    print(f"Failed to remove container: {e}")
            
            job.container_id = None
            self.db.commit()

            # SSE 알림
            await sse_manager.broadcast("status_change", {
                "job_id": job.id, 
                "status": final_status,
                "project_id": job.project_id
            })

            # 작업 완료 -> 다음 큐 실행 트리거
            background_tasks.add_task(self.process_queue)
    
    async def stream_job_logs(self, job_id: int):
        """로그 스트리밍 (Running -> Docker, Finished -> File)"""
        log_path = os.path.join(self.log_dir, f"{job_id}.log")

        # 1. 파일이 생성될 때까지 대기
        for _ in range(10): 
            if os.path.exists(log_path): break
            await asyncio.sleep(0.5)

        if not os.path.exists(log_path):
            for _ in range(20): # 최대 10초 대기
                await asyncio.sleep(0.5)
                if os.path.exists(log_path):
                    break
            else:
                yield "data: [System] 로그 파일 생성 대기 중... (파일이 아직 없습니다)\n\n"

        # 2. 비동기 파일 읽기 시작
        async with aiofiles.open(log_path, mode='r', encoding="utf-8") as f:
            while True:
                line = await f.readline()
                if line:
                    yield f"data: {line.rstrip()}\n\n"
                else:
                    with SessionLocal() as db:
                        job = db.query(Job).filter(Job.id == job_id).first()
                        
                        if not job:
                            yield "data: [System] 작업을 찾을 수 없습니다.\n\n"
                            break
                        if job.status not in [JobStatus.RUNNING.value, JobStatus.PENDING.value]:
                            # 마지막으로 파일에 새로 써진 로그가 있는지 한 번 더 확인
                            remaining = await f.read()
                            if remaining:
                                for r_line in remaining.splitlines():
                                    yield f"data: {r_line}\n\n"
                            
                            yield f"data: [System] 학습이 종료되었습니다. (최종 상태: {job.status})\n\n"
                            break
                    
                    # 아직 실행 중이면 잠깐 대기 후 다시 읽기 (Non-blocking)
                    await asyncio.sleep(0.3)   
    
    def get_active_jobs(self, project_id: int = None) -> List[Job]:
        query = self.db.query(Job).filter(
            Job.status.in_([
                JobStatus.RUNNING.value, 
                JobStatus.PENDING.value
            ])
        )
        
        if project_id:
            query = query.filter(Job.project_id == project_id)
            
        return query.order_by(Job.id.desc()).all()

    def get_job_history(self, project_id: Optional[int], skip: int = 0, limit: int = 20) -> List[Any]:
        # 1. DB에서 먼저 이력 정보를 가져옵니다.
        query = self.db.query(Job).filter(
            Job.status.in_([
                JobStatus.FINISHED.value, 
                JobStatus.FAILED.value,
                JobStatus.CANCELED.value,
                JobStatus.KILLED.value
            ])
        )

        if project_id is not None:
            query = query.filter(Job.project_id == project_id)

        jobs = query.order_by(Job.id.desc()).offset(skip).limit(limit).all()

        # 2. MLflow 일괄 조회를 위한 run_id 리스트 추출
        run_ids = [job.run_id for job in jobs if job.run_id]
        
        if not run_ids:
            for job in jobs: job.metrics = {}
            return jobs

        try:
            # print(f"[MLflow Search] Searching for {len(run_ids)} run_ids...")
            # 3. MLflow search_runs를 사용하여 한 번에 조회
            run_id_str = ", ".join([f"'{rid}'" for rid in run_ids])
            filter_string = f"attributes.run_id IN ({run_id_str})"
            
            # 현재 선택된 프로젝트의 experiment_id들을 중복 제거하여 리스트업 (검색 범위 제한용)
            exp_ids = list(set([job.experiment_id for job in jobs if job.experiment_id]))

            run_id_str = ", ".join([f"'{rid}'" for rid in run_ids])
            filter_string = f"attributes.run_id IN ({run_id_str})"

            # 3. MLflow 조회
            runs = mlflow_provider.client.search_runs(
                experiment_ids=exp_ids,
                filter_string=filter_string,
                max_results=limit
            )

            print(f"[MLflow Result] Found {len(runs)} runs in MLflow.")

            # 4. 조회된 결과를 {run_id: metrics} 형태의 맵으로 변환
            metrics_map = {run.info.run_id: run.data.metrics for run in runs}

            # 5. DB 데이터에 메트릭 결합
            for job in jobs:
                job.metrics = metrics_map.get(job.run_id, {})
                # if not job.metrics:
                #     print(f"[Warning] No metrics found for Run ID: {job.run_id}, {job.experiment_id}")

        except Exception as e:
            print(f"[MLflow Search Error] {e}")
            # 에러 발생 시 빈 객체로 초기화하여 API 응답 규격 유지
            for job in jobs:
                job.metrics = {}

        return jobs
    
    async def get_all_logs(self, job_id: int) -> str:
        """종료된 작업의 로그 파일 전체 내용을 읽어 반환합니다."""
        log_path = os.path.join(self.log_dir, f"{job_id}.log")
        if not os.path.exists(log_path):
            return "[System] 로그 파일이 존재하지 않습니다."
        
        async with aiofiles.open(log_path, mode='r', encoding="utf-8") as f:
            content = await f.read()
            return content