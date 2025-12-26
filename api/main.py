from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, FileResponse
import asyncio, boto3, docker, os, mlflow, traceback, json, bentoml, requests
from datetime import datetime, timedelta, timezone
from mlflow.tracking import MlflowClient
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

app = FastAPI()

# --- 1. CORS 설정 ---
origins = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. DB 설정 (Postgres) ---
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@postgres:5432/{os.getenv('POSTGRES_DB')}"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 1. 한국 표준시(KST) 정의
KST = timezone(timedelta(hours=9))

def get_kst_now():
    """현재 한국 시간을 반환하는 헬퍼 함수"""
    return datetime.now(KST)

class TrainingJob(Base):
    __tablename__ = "training_jobs"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="PENDING") # PENDING, RUNNING, FINISHED, FAILED
    model_variant = Column(String)
    dataset = Column(String)
    epochs = Column(Integer)
    batch = Column(Integer)
    run_id = Column(String, nullable=True)
    container_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_kst_now)
    updated_at = Column(DateTime(timezone=True), default=get_kst_now, onupdate=get_kst_now)

Base.metadata.create_all(bind=engine)

# --- 2. 전역 비동기 큐 및 클라이언트 설정 ---
training_queue = asyncio.Queue()
docker_client = docker.from_env()
MLFLOW_TRACKING_URI = "http://mlflow:5000"
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow_client = MlflowClient()

# --- 2. 클라이언트 초기화 (Docker, MLflow, S3) ---
try:
    docker_client = docker.from_env()
    docker_client.ping()
    print("Docker connected")
except Exception as e:
    print(f"Docker connection error: {e}")
    docker_client = None

s3 = boto3.client('s3',
    endpoint_url=os.getenv('MLFLOW_S3_ENDPOINT_URL', "http://minio:9000"),
    aws_access_key_id=os.getenv('MINIO_ACCESS_KEY', "minio"),
    aws_secret_access_key=os.getenv('MINIO_SECRET_KEY', "minio123")
)

class SSEManager:
    def __init__(self):
        self.subscribers = []

    async def subscribe(self):
        queue = asyncio.Queue()
        self.subscribers.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self.subscribers.remove(queue)

    def broadcast(self, message: dict):
        # 딕셔너리를 JSON 문자열로 변환하여 전송
        data = f"data: {json.dumps(message)}\n\n"
        for queue in self.subscribers:
            queue.put_nowait(data)

sse_manager = SSEManager()


# --- 3. 핵심: 비동기 워커 (Event-Driven Worker) ---
async def training_worker():
    """큐에 작업이 들어오는 '이벤트'가 발생할 때만 즉시 동작합니다."""
    print("Training Worker 가동: 대기열 감시 시작")
    while True:
        # 큐에서 작업이 들어올 때까지 '완전 대기' (폴링 X, CPU 사용 0)
        job_info = await training_queue.get() 
        job_id = job_info["job_id"]
        
        db = SessionLocal()
        try:
            job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
            if not job or job.status == "CANCELLED":
                print(f"Job {job_id}는 취소된 작업이므로 스킵합니다.")
                continue

            # 1. 상태 변경: PENDING -> RUNNING
            job.status = "RUNNING"
            db.commit()
            
            target_model = job.model_variant
            target_dataset = job.dataset
            target_epochs = job.epochs
            target_batch = job.batch

            # 2. 실시간 SSE 전송 (프론트 UI 업데이트용)
            sse_manager.broadcast({"job_id": job_id, "status": "RUNNING", "event": "status_changed"})

            db.close()
            await execute_training_logic_refined(job_id, target_model, target_dataset, target_epochs, target_batch)

        except Exception as e:
            print(f"워커 실행 에러: {e}")
            traceback.print_exc()
        finally:
            db.close()
            training_queue.task_done()

async def execute_training_logic_refined(job_id, model_variant, dataset, epochs, batch):
    """
    실제 도커를 띄우고 MLflow를 연동하는 개선된 로직.
    DB 세션을 짧게 유지하며, 장시간 컨테이너 대기 중에는 세션을 점유하지 않습니다.
    """
    run_id = None
    container = None

    try:
        # 1. MLflow 실험(Experiment) 및 실행(Run) 생성
        exp_name = f"{model_variant}_Experiments"
        exp = mlflow.get_experiment_by_name(exp_name)
        exp_id = exp.experiment_id if exp else mlflow.create_experiment(exp_name)
        
        run = mlflow_client.create_run(experiment_id=exp_id)
        run_id = run.info.run_id

        # 2. 도커 실행 환경 설정
        env_vars = {
            "MLFLOW_RUN_ID": str(run_id),
            "MLFLOW_TRACKING_URI": MLFLOW_TRACKING_URI,
            "MLFLOW_S3_ENDPOINT_URL": "http://minio:9000",
            "DATASET_PATH": dataset,
            "EPOCHS": str(epochs),
            "BATCH": str(batch),
            "AWS_ACCESS_KEY_ID": "minio",
            "AWS_SECRET_ACCESS_KEY": "minio123"
        }

        train_script = "train_yolo.py" if model_variant == "YOLOv8" else "train_effnet.py"
        log_command = f"sh -c 'mkdir -p /app/runs && python {train_script} 2>&1 | tee /app/runs/$(hostname).log'"

        # 3. Docker 컨테이너 실행 (비동기 루프 방해하지 않게 detach=True)
        container = docker_client.containers.run(
            image="mlops_kitech-training",
            command=log_command,
            environment=env_vars,
            shm_size="8G",
            network="mlops_kitech_mlops-net",
            volumes={'mlops_kitech_mlops_training_logs': {'bind': '/app/runs', 'mode': 'rw'}},
            device_requests=[docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])],
            detach=True
        )

        short_id = container.id[:12]

        sse_manager.broadcast({
            "job_id": job_id, 
            "container_id": short_id, 
            "event": "container_created"
        })

        # 4. DB 정보 업데이트 (짧은 세션 사용)
        db = SessionLocal()
        try:
            job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
            if job:
                job.run_id = run_id
                job.container_id = container.id
                db.commit()

                mlflow_client.set_tag(run_id, "container_id", short_id)
                print(f"Job {job_id} 업데이트 완료: Run ID={run_id}, Container={container.id[:12]}")
        finally:
            db.close() # 업데이트 후 즉시 세션 종료

        # 5. 컨테이너 종료 대기 (DB 세션 없이 루프 진행)
        print(f"컨테이너 {short_id} 종료 대기 중...")
        result = await asyncio.to_thread(container.wait)

        print(f"컨테이너 {short_id} 실행 종료됨 (Status: {container.status})")

        log_path = f"/app/runs/{short_id}.log"
        if os.path.exists(log_path):
            print("로그 확인 완료")
    except Exception as e:
        print(f"execute_training_logic_refined 에러: {e}")
        # 에러 발생 시 DB 상태를 FAILED로 변경
        db = SessionLocal()
        try:
            job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
            if job:
                job.status = "FAILED"
                db.commit()
            if run_id:
                mlflow_client.set_terminated(run_id, status="FAILED")
        finally:
            db.close()
    
    finally:
        # if container:
        #     try:
        #         container.remove(force=True)
        #     except Exception as e:
        #         print(f"컨테이너 삭제 중 오류: {e}")

        if run_id and container:
            asyncio.create_task(watch_run_status_and_db(run_id, short_id, job_id))

async def watch_run_status_and_db(run_id, container_id, job_id):
    """MLflow 상태를 감시하여 DB의 최종 상태까지 업데이트합니다."""
    while True:
        try:
            run = mlflow_client.get_run(run_id)
            status = run.info.status
            if status != "RUNNING":
                db = SessionLocal()
                job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
                job.status = status # FINISHED, FAILED 등
                db.commit()
                db.close()
                
                sse_manager.broadcast({"run_id": run_id, "job_id": job_id, "status": status, "event": "status_changed"})
                break
        except: break
        await asyncio.sleep(5)

# --- 3. 데이터 모델 ---
class TrainRequest(BaseModel):
    dataset: str
    epochs: int
    batch: int
    model_variant: str

async def bento_build_process(run_id: str):
    try:
        # 1. 빌드 시작 알림
        sse_manager.broadcast({"run_id": run_id, "status": "BUILDING", "event": "bento_status", "message": "가중치 다운로드 중..."})

        # 2. MLflow에서 가중치만 다운로드 (로그 폭탄 방지)
        # 특정 파일만 지정했으므로 이전보다 훨씬 빠르고 깔끔합니다.
        artifact_path = mlflow.artifacts.download_artifacts(
            run_id=run_id, 
            artifact_path="weights/best.pt"
        )
        
        # 3. BentoML 모델 등록
        sse_manager.broadcast({"run_id": run_id, "event": "bento_log", "message": "BentoML 모델 저장소 등록 중..."})
        bentoml.models.create(
            "yolo_v8_pcb_model",
            custom_objects={"model.pt": artifact_path},
            labels={"run_id": run_id}
        )
        
        # 4. 비동기 서브프로세스로 빌드 실행 (중요: 이벤트 루프를 방해하지 않음)
        sse_manager.broadcast({"run_id": run_id, "event": "bento_log", "message": "BentoML 빌드 시작 (Dockerizing)..."})
        
        # subprocess.run 대신 asyncio.create_subprocess_exec 사용
        process = await asyncio.create_subprocess_exec(
            "bentoml", "build",
            cwd="./api", # bentofile.yaml이 있는 위치
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )

        # 5. 빌드 로그 실시간 캡처 및 프론트 전송
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            log_msg = line.decode('utf-8').strip()
            # 프론트엔드 터미널로 실시간 로그 전송
            sse_manager.broadcast({
                "run_id": run_id, 
                "event": "bento_log", 
                "message": log_msg
            })

        await process.wait()

        if process.returncode == 0:
            sse_manager.broadcast({"run_id": run_id, "status": "SUCCESS", "event": "bento_status", "message": "배포 준비 완료"})
        else:
            sse_manager.broadcast({"run_id": run_id, "status": "FAILED", "event": "bento_status", "message": "빌드 실패"})

    except Exception as e:
        traceback.print_exc()
        sse_manager.broadcast({
            "run_id": run_id, 
            "status": "FAILED", 
            "event": "bento_status", 
            "message": f"에러 발생: {str(e)}"
        })

# --- 4. MLflow 실험 및 실행 내역 조회 API ---
@app.get("/experiments")
async def get_experiments():
    """MLflow의 모든 실험 목록을 가져옵니다."""
    try:
        # Default(0) 실험을 포함하여 모든 실험 반환
        exps = mlflow_client.search_experiments()
        return [
            {
                "experiment_id": e.experiment_id,
                "name": e.name,
                "lifecycle_stage": e.lifecycle_stage
            } for e in exps
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/experiments/{experiment_id}/runs")
async def get_runs(experiment_id: str):
    """특정 실험에 속한 모든 실행(Run) 항목을 가져옵니다."""
    try:
        runs = mlflow_client.search_runs(
            experiment_ids=[experiment_id],
            order_by=["attributes.start_time DESC"]
        )
        
        results = []
        for run in runs:
            results.append({
                "run_id": run.info.run_id,
                "run_name": run.data.tags.get("mlflow.runName", "No Name"),
                "status": run.info.status,
                "start_time": run.info.start_time,
                "end_time": run.info.end_time,
                "metrics": run.data.metrics,
                "params": run.data.params,
                "tags": run.data.tags
            })
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 5. 데이터셋 및 버킷 조회 API ---

@app.get("/datasets")
async def get_datasets():
    try:
        response = s3.list_buckets()
        return {"datasets": [b['Name'] for b in response['Buckets']]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/buckets/{bucket_name}/browse")
async def browse_bucket(bucket_name: str, prefix: str = ""):
    try:
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, Delimiter='/')
        folders = [p['Prefix'] for p in response.get('CommonPrefixes', [])]
        files = [{"name": obj['Key'].split('/')[-1], "full_path": obj['Key'], "size": obj['Size']} 
                 for obj in response.get('Contents', []) if obj['Key'] != prefix]
        return {"current_path": prefix, "folders": folders, "files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.on_event("startup")
async def startup_event():
    # 1. 서버 시작 시 워커 기동
    asyncio.create_task(training_worker())
    
    # 2. [Persistence] DB에 PENDING 상태로 남은 작업들 큐에 다시 삽입
    db = SessionLocal()
    pending_jobs = db.query(TrainingJob).filter(TrainingJob.status == "PENDING").order_by(TrainingJob.created_at.asc()).all()
    for job in pending_jobs:
        training_queue.put_nowait({"job_id": job.id})
    db.close()
    print(f"📦 {len(pending_jobs)}개의 대기 중인 작업을 큐에 복구했습니다.")

# --- 6. 학습 시작 API ---
@app.post("/train")
async def start_training(req: TrainRequest):
    """학습 버튼 클릭 시 DB 저장 및 큐에 즉시 삽입"""
    db = SessionLocal()
    try:
        new_job = TrainingJob(
            model_variant=req.model_variant,
            dataset=req.dataset,
            epochs=req.epochs,
            batch=req.batch,
            status="PENDING"
        )
        db.add(new_job)
        db.commit()
        db.refresh(new_job)

        # 큐에 즉시 던짐 (워커가 즉시 감지)
        training_queue.put_nowait({"job_id": new_job.id})

        # 프론트에 "대기열에 들어갔음" 알림
        sse_manager.broadcast({"job_id": new_job.id, "status": "PENDING", "event": "job_queued"})
        
        return {"status": "Queued", "job_id": new_job.id}
    finally:
        db.close()

# --- [추가] 진행 중인 작업 목록 조회 API ---
@app.get("/jobs/active")
async def get_active_jobs():
    """PENDING 또는 RUNNING 상태인 모든 작업을 반환합니다."""
    db = SessionLocal()
    jobs = db.query(TrainingJob).filter(TrainingJob.status.in_(["PENDING", "RUNNING"])).order_by(TrainingJob.created_at.asc()).all()
    db.close()
    return jobs

# --- [추가] 모든 완료/실패/취소된 작업 조회 API ---
@app.get("/jobs/history")
async def get_job_history():
    """FINISHED, FAILED, CANCELLED 상태인 모든 기록을 반환합니다."""
    db = SessionLocal()
    try:
        # 이력은 보통 최신순(created_at DESC)으로 보는 것이 편합니다.
        jobs = db.query(TrainingJob)\
                 .filter(TrainingJob.status.in_(["FINISHED", "FAILED", "CANCELLED"]))\
                 .order_by(TrainingJob.created_at.desc()).all()
        return jobs
    finally:
        db.close()

@app.post("/jobs/{job_id}/cancel")
async def cancel_training_job(job_id: int):
    db = SessionLocal()
    try:
        job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

        # 1. 대기 중인 경우: DB 상태만 변경 (워커가 나중에 스킵함)
        if job.status == "PENDING":
            job.status = "CANCELLED"
            job.updated_at = get_kst_now()
            db.commit()
            sse_manager.broadcast({"job_id": job_id, "status": "CANCELLED", "event": "status_changed"})
            return {"message": "대기열에서 작업이 취소되었습니다."}

        # 2. 실행 중인 경우: 도커 중지 및 MLflow 종료 처리
        if job.status == "RUNNING":
            # 도커 컨테이너 강제 중지 및 삭제
            if job.container_id:
                try:
                    container = docker_client.containers.get(job.container_id)
                    container.remove(force=True)
                except Exception as e:
                    print(f"⚠️ 컨테이너 삭제 중 오류: {e}")

            # MLflow Run 종료 처리
            if job.run_id:
                mlflow_client.set_terminated(job.run_id, status="KILLED")

            job.status = "CANCELLED"
            job.updated_at = get_kst_now()
            db.commit()
            sse_manager.broadcast({"job_id": job_id, "status": "CANCELLED", "event": "status_changed"})
            return {"message": "실행 중인 학습이 중단되었습니다."}

        return {"message": "이미 완료되었거나 취소할 수 없는 상태입니다."}
    finally:
        db.close()

# --- 7. [유지] 컨테이너 로그 실시간 스트리밍 (SSE) ---
@app.get("/train/{container_id}/logs")
async def stream_logs(container_id: str):
    log_file_path = f"/app/runs/{container_id[:12]}.log"

    def generate_logs():
        try:
            try:
                container = docker_client.containers.get(container_id)
                # stream=True, follow=True를 통해 실시간 로그 획득
                for line in container.logs(stream=True, follow=True, tail=100):
                    yield f"data: {line.decode('utf-8')}\n\n"
            except docker.errors.NotFound:
                if os.path.exists(log_file_path):
                    with open(log_file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            yield f"data: {line}\n\n"
                else:
                    yield f"data: Error: No active container or saved log file found for {container_id}.\n\n"
        except Exception as e:    
            yield f"data: Unexpected error: {str(e)}\n\n"

    return StreamingResponse(generate_logs(), media_type="text/event-stream")

@app.get("/train/status-stream")
async def status_stream():
    return StreamingResponse(sse_manager.subscribe(), media_type="text/event-stream")

@app.get("/runs/{run_id}/metrics/history")
async def get_metrics_history(run_id: str):
    try:
        metric_mapping = {
            "metrics.mAP50(B)": "metrics/mAP50B",
            "metrics.mAP50-95(B)": "metrics/mAP50-95B",
            "train.box_loss": "train/box_loss",
            "train.cls_loss": "train/cls_loss"
        }
        history_data = {}
        
        for frontend_key, mlflow_key in metric_mapping.items():
            try:
                # 2. MLflow에서 해당 지표의 전체 이력(Step별 값)을 가져옴
                history = mlflow_client.get_metric_history(run_id, mlflow_key)
                
                # 3. 프론트엔드가 인식할 수 있는 키 이름으로 배열 저장
                history_data[frontend_key] = [m.value for m in history]
            except Exception as e:
                print(f"{mlflow_key} 데이터를 가져오는데 실패: {e}")
                history_data[frontend_key] = []
        
        return history_data
    
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/runs/{run_id}/artifacts/preview")
async def get_artifact_preview(run_id: str, filename: str = "val_batch0_labels.jpg"):
    try:
        cache_dir = f"./artifact_cache/{run_id}"
        local_path = os.path.join(cache_dir, filename)

        # 2. 파일이 이미 로컬에 존재하면 바로 반환 (네트워크 작업 스킵)
        if os.path.exists(local_path):
            return FileResponse(local_path)
        
        print(f"캐시 없음, MLflow에서 다운로드 시도: run_id={run_id}, filename={filename}")

        # MLflow 아티팩트 루트에서 파일을 직접 찾습니다.
        # 제시하신 S3 경로상 파일이 artifacts/ 바로 아래에 있으므로 상대 경로는 filename 그 자체입니다.
        downloaded_path = mlflow.artifacts.download_artifacts(
            run_id=run_id, 
            artifact_path=filename,
            dst_path=cache_dir # 캐시 디렉토리에 저장
        )
        
        return FileResponse(downloaded_path)

    except Exception as e:
        print(f"아티팩트 다운로드 실패: {e}")
        traceback.print_exc() # 상세 에러 스택 확인용
        # 디버깅을 위해 상세 에러 메시지 반환
        raise HTTPException(status_code=404, detail=f"이미지 로드 실패: {str(e)}")
    
@app.post("/runs/{run_id}/deploy")
async def deploy_model(run_id: str, background_tasks: BackgroundTasks):
    """사용자가 버튼을 눌렀을 때 배포 프로세스를 시작합니다."""
    # 1. 먼저 배포 시작 알림을 보냄
    sse_manager.broadcast({"run_id": run_id, "status": "BUILDING", "event": "bento_status"})
    
    # 2. 백그라운드에서 빌드 및 서빙 프로세스 실행
    background_tasks.add_task(bento_build_process, run_id)
    
    return {"message": "BentoML 배포가 시작되었습니다.", "run_id": run_id}

@app.post("/runs/{run_id}/predict")
async def predict_sample(run_id: str, file: UploadFile = File(...)):
    """배포된 BentoML 서비스로 이미지를 보내 추론 결과를 받아옵니다."""
    # BentoML 서버 주소 (배포 로직에서 결정된 포트나 URL)
    bento_url = "http://localhost:3000/predict" 
    
    files = {"img": (file.filename, file.file, file.content_type)}
    response = requests.post(bento_url, files=files)
    
    return response.json()

# --- [추가] 1. 상태별 Run 검색 API ---
@app.get("/runs/status/{status}")
async def get_runs_by_status(status: str):
    """모든 실험에서 특정 상태(예: FINISHED)인 Run들만 모아서 반환합니다."""
    try:
        # 모든 실험 ID 가져오기
        exps = mlflow_client.search_experiments()
        exp_ids = [e.experiment_id for e in exps]
        
        if not exp_ids:
            return []

        # 모든 실험에서 해당 상태인 Run 검색
        # filter_string 사용: "attributes.status = 'FINISHED'"
        runs = mlflow_client.search_runs(
            experiment_ids=exp_ids,
            filter_string=f"attributes.status = '{status}'",
            order_by=["attributes.start_time DESC"]
        )
        
        results = []
        for run in runs:
            results.append({
                "run_id": run.info.run_id,
                "run_name": run.data.tags.get("mlflow.runName", "No Name"),
                "status": run.info.status,
                "start_time": run.info.start_time,
                "metrics": run.data.metrics,
                "tags": run.data.tags
            })
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- [추가] 2. 활성 서비스 조회 API ---
@app.get("/deployments/active")
async def get_active_services():
    """현재 Docker에서 실행 중인 BentoML 추론 서버 컨테이너를 찾아 목록을 반환합니다."""
    if docker_client is None:
        return []
    
    try:
        # 'bentoml' 관련 컨테이너나 특정 라벨이 붙은 컨테이너 필터링
        # 여기서는 예시로 모든 실행 중인 컨테이너 중 이름에 'bento'가 포함된 것을 찾습니다.
        containers = docker_client.containers.list()
        active_list = []
        
        for c in containers:
            if "bento" in c.name or "serving" in c.name:
                active_list.append({
                    "id": c.id[:12],
                    "name": c.name,
                    "status": c.status, # 'running'
                    "url": f"http://localhost:3000", # 실제로는 컨테이너 포트 매핑 정보 확인 필요
                    "run_id": c.labels.get("run_id", "Unknown")
                })
        return active_list
    except Exception as e:
        return []

# --- [수정] 3. 추론 요청 API (매개변수명 일치) ---
@app.post("/runs/{run_id}/predict")
async def predict_sample(run_id: str, file: UploadFile = File(...)):
    """프론트엔드에서 보낸 이미지를 받아 BentoML 서버로 전달합니다."""
    # 현재 배포된 BentoML 서비스 주소 (Docker 네트워크 이름 혹은 localhost)
    # 실제 운영 시에는 run_id에 맞는 컨테이너 포트를 동적으로 찾아야 함
    BENTO_URL = "http://localhost:3000/predict" 
    
    try:
        contents = await file.read()
        # BentoML 서비스로 파일 전달
        files = {"img": (file.filename, contents, file.content_type)}
        response = requests.post(BENTO_URL, files=files, timeout=10)
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="BentoML Inference Error")
            
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference Connection Failed: {str(e)}")