from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import asyncio
import boto3
import docker
import os
import mlflow
from mlflow.tracking import MlflowClient
import traceback

app = FastAPI()

try:
    # 환경변수나 마운트된 소켓을 자동으로 감지합니다.
    client = docker.from_env() 
    client.ping() # 연결 확인
    print("✅ [성공] Docker 엔진과 연결되었습니다.")
except Exception as e:
    print(f"❌ [실패] Docker 연결 오류: {e}")
    client = None

# 1. CORS 설정 (이미 잘 하셨습니다!)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. 전송받을 데이터 규격 정의 (Angular에서 보낸 JSON을 파싱)
class TrainRequest(BaseModel):
    dataset: str
    epochs: int
    batch: int
    model_variant: str

# MinIO 설정
s3 = boto3.client('s3',
    endpoint_url=os.getenv('MLFLOW_S3_ENDPOINT_URL', "http://minio:9000"),
    aws_access_key_id=os.getenv('MINIO_ACCESS_KEY', "minio"),
    aws_secret_access_key=os.getenv('MINIO_SECRET_KEY', "minio123")
)

@app.get("/datasets")
async def get_datasets():
    """MinIO에서 버킷 목록을 가져와서 데이터셋 리스트로 반환"""
    try:
        response = s3.list_buckets()
        return {"datasets": [b['Name'] for b in response['Buckets']]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/buckets/{bucket_name}/browse")
async def browse_bucket(bucket_name: str, prefix: str = ""):
    """
    특정 버킷 내의 특정 경로(prefix) 하위 폴더 및 파일 목록을 반환합니다.
    """
    try:
        # Delimiter를 '/'로 설정하면 S3는 해당 경로 바로 아래의 '폴더'들을 그룹화해서 반환합니다.
        response = s3.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
            Delimiter='/'
        )

        # 1. 하위 폴더 목록 추출 (CommonPrefixes)
        folders = []
        if 'CommonPrefixes' in response:
            folders = [p['Prefix'] for p in response['CommonPrefixes']]

        # 2. 파일 목록 추출 (Contents)
        files = []
        if 'Contents' in response:
            for obj in response['Contents']:
                # Prefix와 완전히 일치하는 경우는 폴더 자체이므로 제외
                if obj['Key'] == prefix:
                    continue
                
                files.append({
                    "name": obj['Key'].split('/')[-1], # 전체 경로에서 파일명만 추출
                    "full_path": obj['Key'],
                    "size": obj['Size'],
                    "last_modified": obj['LastModified'].isoformat()
                })

        return {
            "current_path": prefix,
            "folders": folders,
            "files": files
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/train")
async def start_training(req: dict):
    # 만약 client가 None이라면 실행 전 미리 알려줌
    if client is None:
        raise HTTPException(
            status_code=500, 
            detail="백엔드 서버가 Docker 엔진과 연결되지 않았습니다. 관리자에게 문의하세요."
        )
    
    try:
        model_variant = req.get("model_variant")
        params = req.get("params", {})
        dataset = req.get("dataset")

        # 1. 모델별 이미지 매핑 (실제 빌드된 이미지명으로 확인하세요)
        # 터미널에서 'docker images'를 쳐서 나오는 이름을 적어야 합니다.
        image_map = {
            "YOLOv8": "mlops_kitech-training", 
            "EfficientNet": "mlops_kitech-training"
        }
        target_image = image_map.get(model_variant)

        # 2. MLflow 설정
        mlflow.set_tracking_uri("http://mlflow:5000")
        mlflow.set_experiment(f"{model_variant}_Experiments")
        
        with mlflow.start_run() as run:
            run_id = run.info.run_id
            
            # 3. 환경 변수 안전하게 구성 (None 방지)
            env_vars = {
                "MLFLOW_RUN_ID": str(run_id),
                "MLFLOW_TRACKING_URI": "http://mlflow:5000",
                "MLFLOW_S3_ENDPOINT_URL": "http://minio:9000",
                "DATASET_PATH": str(dataset) if dataset else "",

                # ✅ 수정 포인트: 백엔드 컨테이너가 가진 'MINIO_ACCESS_KEY'를 가져옵니다.
                # 이것을 학습 컨테이너(boto3)가 인식하는 'AWS_ACCESS_KEY_ID'로 매핑합니다.
                "AWS_ACCESS_KEY_ID": os.getenv('MINIO_ACCESS_KEY'), 
                "AWS_SECRET_ACCESS_KEY": os.getenv('MINIO_SECRET_KEY'),
                
                "EPOCHS": str(params.get('epochs', 1)),
                "BATCH": str(params.get('batch', 8)),
                "MODEL_VARIANT": str(params.get('model_variant', 'yolov8n.pt'))
            }

            print(f"DEBUG: 실행할 이미지 -> {target_image}")
            print(f"DEBUG: 네트워크 -> mlops_kitech_mlops-net") # 프로젝트명 확인 필요

            # 4. 컨테이너 실행
            container = client.containers.run(
                image=target_image,
                command=f"python train_yolo.py" if model_variant == "YOLOv8" else "python train_effnet.py",
                environment=env_vars,
                shm_size="8G",
                network="mlops_kitech_mlops-net", 
                device_requests=[docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])],
                detach=True
            )

        return {
            "status": "Success",
            "container_id": container.id,
            "run_id": run_id,
            "mlflow_url": f"http://localhost:5000/#/experiments/{run.info.experiment_id}/runs/{run_id}"
        }
    except Exception as e:
        # 에러의 상세 내용을 백엔드 터미널에 출력합니다.
        print("❌ 상세 에러 발생:")
        traceback.print_exc() 
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/models")
async def get_trained_models():
    """MLflow에서 실험(Run) 이력을 조회하여 성공한 모델 리스트 반환"""
    try:
        mlflow.set_tracking_uri("http://mlflow:5000")
        # 모든 실험 데이터 가져오기 (최근 순)
        runs = mlflow.search_runs(experiment_names=["YOLOv8_Manufacturing_Test"], order_by=["start_time DESC"])
        
        # UI에서 보기 좋게 필요한 정보만 추출
        model_list = []
        for _, run in runs.iterrows():
            model_list.append({
                "run_id": run["run_id"],
                "start_time": run["start_time"],
                "status": run["status"],
                "epochs": run.get("params.epochs", "N/A"),
                "mAP50": run.get("metrics.metrics/mAP50(B)", "N/A") # YOLOv8 지표 이름
            })
        return {"models": model_list}
    except Exception as e:
        # 아직 실험이 없으면 빈 리스트 반환
        return {"models": []}
    
@app.get("/train/{container_id}/logs")
async def stream_logs(container_id: str):
    """특정 컨테이너의 로그를 실시간으로 스트리밍합니다."""
    def generate_logs():
        try:
            container = client.containers.get(container_id)
            # stream=True, follow=True를 통해 실시간 로그 제너레이터 생성
            log_generator = container.logs(stream=True, follow=True, tail=100)
            
            for line in log_generator:
                # SSE 형식에 맞춰 'data: ' 접두사 필요
                yield f"data: {line.decode('utf-8')}\n\n"
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

    return StreamingResponse(generate_logs(), media_type="text/event-stream")