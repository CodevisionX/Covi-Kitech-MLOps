from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, File, UploadFile  # ✅ File, UploadFile 추가
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, FileResponse
import asyncio
import boto3
import docker
import os
import mlflow
from mlflow.tracking import MlflowClient
import traceback
import json
import bentoml
import shutil
import requests

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

# --- 2. 클라이언트 초기화 (Docker, MLflow, S3) ---
try:
    docker_client = docker.from_env()
    docker_client.ping()
    print("✅ Docker connected")
except Exception as e:
    print(f"❌ Docker connection error: {e}")
    docker_client = None

MLFLOW_TRACKING_URI = "http://mlflow:5000"
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow_client = MlflowClient()

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

# --- 2. 학습 상태 추적 백그라운드 태스크 ---
async def watch_run_status(run_id: str, container_id: str):
    """특정 학습 건의 종료를 감시하고 프론트에 알립니다."""
    print(f"👀 모니터링 시작: {run_id}")
    while True:
        try:
            run = mlflow_client.get_run(run_id)
            status = run.info.status
            
            # 상태가 RUNNING이 아니면 (FINISHED, FAILED 등) 결과 전송 후 종료
            if status != "RUNNING":
                sse_manager.broadcast({
                    "run_id": run_id,
                    "status": status,
                    "event": "status_changed"
                })
                print(f"✅ 모니터링 종료: {run_id} (상태: {status})")
                break
        except Exception as e:
            print(f"⚠️ 모니터링 에러: {e}")
            break
        
        await asyncio.sleep(5) # 5초마다 MLflow만 체크 (부하 적음)

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

# --- 6. 학습 시작 API ---
@app.post("/train")
async def start_training(req: TrainRequest, background_tasks: BackgroundTasks): # 1. background_tasks 주입
    if docker_client is None:
        raise HTTPException(status_code=500, detail="Docker connection failed")
    try:
        # 1. 실험 ID 가져오기 또는 생성
        exp = mlflow.get_experiment_by_name(f"{req.model_variant}_Experiments")
        if exp is None:
            exp_id = mlflow.create_experiment(f"{req.model_variant}_Experiments")
        else:
            exp_id = exp.experiment_id

        # 2. 수동으로 Run 생성 (기본 상태는 RUNNING)
        run = mlflow_client.create_run(experiment_id=exp_id)
        run_id = run.info.run_id

        env_vars = {
            "MLFLOW_RUN_ID": str(run_id),
            "MLFLOW_TRACKING_URI": MLFLOW_TRACKING_URI,
            "MLFLOW_S3_ENDPOINT_URL": "http://minio:9000",
            "DATASET_PATH": req.dataset,
            "AWS_ACCESS_KEY_ID": "minio",
            "AWS_SECRET_ACCESS_KEY": "minio123",
            "EPOCHS": str(req.epochs),
            "BATCH": str(req.batch)
        }

        # 3. 도커 실행
        container = docker_client.containers.run(
            image="mlops_kitech-training",
            command=f"python train_yolo.py" if req.model_variant == "YOLOv8" else "python train_effnet.py",
            environment=env_vars,
            shm_size="8G",
            network="mlops_kitech_mlops-net",
            device_requests=[docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])],
            detach=True
        )

        # 4. 태그 설정
        mlflow_client.set_tag(run_id, "container_id", container.id)
        mlflow_client.set_tag(run_id, "algorithm", req.model_variant)
        mlflow_client.set_tag(run_id, "dataset", req.dataset)
        
        # --- [추가] 5. 실시간 상태 업데이트 전송 ---
        # 학습이 시작되었음을 즉시 프론트에 알림
        sse_manager.broadcast({
            "run_id": run_id,
            "status": "RUNNING",
            "event": "started"
        })

        # --- [추가] 6. 백그라운드 모니터링 태스크 등록 ---
        # 이 함수는 API 응답이 나간 뒤 백그라운드에서 실행됩니다.
        background_tasks.add_task(watch_run_status, run_id, container.id)
        
        return {"status": "Success", "container_id": container.id, "run_id": run_id}
            
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# --- 7. [유지] 컨테이너 로그 실시간 스트리밍 (SSE) ---

@app.get("/train/{container_id}/logs")
async def stream_logs(container_id: str):
    """특정 학습 컨테이너의 로그를 실시간으로 스트리밍합니다."""
    def generate_logs():
        try:
            container = docker_client.containers.get(container_id)
            # stream=True, follow=True를 통해 실시간 로그 획득
            for line in container.logs(stream=True, follow=True, tail=100):
                yield f"data: {line.decode('utf-8')}\n\n"
        except Exception as e:
            yield f"data: Error fetching logs: {str(e)}\n\n"

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
                print(f"⚠️ {mlflow_key} 데이터를 가져오는데 실패: {e}")
                history_data[frontend_key] = []
        
        return history_data
    
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/runs/{run_id}/artifacts/preview")
async def get_artifact_preview(run_id: str, filename: str = "val_batch0_labels.jpg"):
    try:
        print(f"📂 다운로드 시도: run_id={run_id}, filename={filename}")

        # MLflow 아티팩트 루트에서 파일을 직접 찾습니다.
        # 제시하신 S3 경로상 파일이 artifacts/ 바로 아래에 있으므로 상대 경로는 filename 그 자체입니다.
        local_path = mlflow.artifacts.download_artifacts(
            run_id=run_id, 
            artifact_path=filename  # 'exp/'를 제거했습니다.
        )
        
        if os.path.exists(local_path):
            return FileResponse(local_path)
        else:
            raise HTTPException(status_code=404, detail="파일을 다운로드했지만 로컬에서 찾을 수 없습니다.")

    except Exception as e:
        print(f"❌ 아티팩트 다운로드 실패: {e}")
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