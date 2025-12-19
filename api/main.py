from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel # 데이터 모델 정의용
import boto3
import docker
import os
import mlflow
from mlflow.tracking import MlflowClient

app = FastAPI()

try:
    client = docker.DockerClient(base_url='unix://var/run/docker.sock')
except Exception as e:
    print(f"Docker 소켓 연결 실패: {e}")
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
async def start_training(req: TrainRequest): # Pydantic 모델 사용
    """UI에서 받은 JSON 데이터로 학습 컨테이너 실행"""
    try:
        # 주의: image 이름은 docker-compose에서 빌드된 실제 이미지명과 일치해야 합니다.
        # 보통 '프로젝트명_training' 형식이거나 빌드 시 지정한 태그명을 사용합니다.
        container = client.containers.run(
            image="mlops_kitech-training", # docker-compose build 시 생성된 이미지명 확인 필요
            environment={
                "EPOCHS": str(req.epochs),
                "BATCH": str(req.batch),
                "MODEL_VARIANT": req.model_variant,
                "DATASET_NAME": req.dataset,
                "MLFLOW_TRACKING_URI": "http://mlflow:5000",
                "MLFLOW_S3_ENDPOINT_URL": "http://minio:9000",
                "AWS_ACCESS_KEY_ID": os.getenv('MINIO_ACCESS_KEY'),
                "AWS_SECRET_ACCESS_KEY": os.getenv('MINIO_SECRET_KEY')
            },
            network="mlops_kitech_mlops-net", # 아까 확인하신 네트워크 이름
            device_requests=[
                docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])
            ],
            detach=True
        )
        return {"status": "Training Started", "container_id": container.id}
    except Exception as e:
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