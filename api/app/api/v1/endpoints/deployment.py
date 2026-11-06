import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.dependencies import get_db
from app.models.job import Job
from app.models.deployment import Deployment
from app.schemas.deployment import DeploymentCreate, DeploymentResponse
import base64
import json

from app.core.constants import PYFUNC_SERVING_MODELS, MODEL_DATASET_TASKS, DatasetTask
from app.services.deployment_service import SERVING_PORT, deployment_service, serving_host
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
    query = db.query(Deployment).join(Job, Deployment.job_id == Job.id).filter(
        Deployment.status.in_(["PENDING", "REGISTERING", "BUILDING", "CREATING", "RUNNING"])
    )

    deployments = query.all()
    for d in deployments:
        exp_id = d.job.experiment_id 
        run_id = d.run_id
        if d.model_family == "yolo":
            d.artifact_uri = f"s3://mlflow-artifacts/{exp_id}/{run_id}/artifacts/plots/weights/best.pt"
    
    return deployments

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

def _is_timeseries(dep: Deployment) -> bool:
    return MODEL_DATASET_TASKS.get(dep.model_family) == DatasetTask.TIMESERIES.value


async def _invoke_pyfunc(dep: Deployment, items: List[str], params: Optional[dict]):
    """MLflow 서빙(/invocations)에 base64 목록을 보냅니다 (이미지 모델은 이미지, 시계열 모델은 .npy)."""
    column = "npy" if _is_timeseries(dep) else "image"
    body = {"dataframe_split": {"columns": [column], "data": [[x] for x in items]}}
    if params:
        body["params"] = params
    url = f"http://{serving_host(dep)}:{SERVING_PORT}/invocations"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json=body, timeout=120.0)
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"서빙 컨테이너 연결 실패: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=f"모델 추론 오류: {r.text[:2000]}")
    return r.json().get("predictions")


def _running(db: Session, deployment_id: int) -> Deployment:
    dep = db.query(Deployment).get(deployment_id)
    if not dep or not dep.container_id:
        raise HTTPException(status_code=404, detail="배포 정보를 찾을 수 없거나 컨테이너가 실행 중이지 않습니다.")
    return dep


@router.post("/{deployment_id}/predict")
async def predict_data(
    deployment_id: int, 
    payload: dict, # JSON 데이터 수신
    db: Session = Depends(get_db)    
):
    """
    YOLO26 / PP-OCRv6: {"images": [base64 PNG/JPEG, ...], "params": {"conf": 0.25, ...}}
      -> {"status": "success", "prediction": [이미지별 결과]}
      검출 결과: {"boxes": [[x1, y1, x2, y2, conf, cls], ...]}, 인식 결과: {"text": "1948", "score": 0.99}
    기존 모델(1D-CNN 등): BentoML /predict 규격 그대로 전달
    """
    dep = _running(db, deployment_id)
    if _is_timeseries(dep):
        items = payload.get("npy")
        if items is None and payload.get("inputs") is not None:
            items = [_npy_b64(payload["inputs"])]
        if not isinstance(items, list) or not items or not all(isinstance(i, str) for i in items):
            raise HTTPException(status_code=422,
                                detail="npy 에 base64 .npy 목록, 또는 inputs 에 (샘플, 윈도[, 채널]) 숫자 배열이 필요합니다")
        preds = await _invoke_pyfunc(dep, items, None)
        return {"status": "success", "model": dep.model_family, "prediction": preds}
    if dep.model_family in PYFUNC_SERVING_MODELS:
        images = payload.get("images")
        if not isinstance(images, list) or not images or not all(isinstance(i, str) for i in images):
            raise HTTPException(status_code=422, detail="images 에 base64 이미지 문자열 목록이 필요합니다")
        preds = await _invoke_pyfunc(dep, images, payload.get("params"))
        return {"status": "success", "model": dep.model_family, "prediction": preds}

    target_url = f"http://{serving_host(dep)}:3000/predict"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(target_url, json=payload, timeout=10.0)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/{deployment_id}/predict/image")
async def predict_image(
    deployment_id: int,
    upload_file: UploadFile = File(...),
    params: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """[YOLO26 / PP-OCRv6] 이미지 파일 하나를 올려 결과를 JSON 으로 받습니다. params 는 JSON 문자열(선택)."""
    dep = _running(db, deployment_id)
    if dep.model_family not in PYFUNC_SERVING_MODELS or _is_timeseries(dep):
        raise HTTPException(status_code=400, detail="이미지 모델(검출·인식) 배포에서만 사용할 수 있습니다")
    try:
        extra = json.loads(params) if params else None
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="params 는 JSON 문자열이어야 합니다")
    image = base64.b64encode(await upload_file.read()).decode()
    preds = await _invoke_pyfunc(dep, [image], extra)
    return {"status": "success", "model": dep.model_family, "prediction": preds[0] if preds else None}


@router.post("/{deployment_id}/predict/npy")
async def predict_npy(deployment_id: int, upload_file: UploadFile = File(...), db: Session = Depends(get_db)):
    """[시계열 1D-CNN] .npy 파일 하나(샘플 1개 또는 여러 개)를 올려 예측합니다."""
    dep = _running(db, deployment_id)
    if not _is_timeseries(dep):
        raise HTTPException(status_code=400, detail="시계열 모델 배포에서만 사용할 수 있습니다")
    raw = await upload_file.read()
    preds = await _invoke_pyfunc(dep, [base64.b64encode(raw).decode()], None)
    return {"status": "success", "model": dep.model_family, "prediction": preds[0] if preds else None}


def _npy_b64(values) -> str:
    import io
    import numpy as np

    try:
        arr = np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="inputs 는 숫자 배열이어야 합니다")
    buf = io.BytesIO()
    np.save(buf, arr, allow_pickle=False)
    return base64.b64encode(buf.getvalue()).decode()


@router.post("/{deployment_id}/predict/visual")
async def predict_visual(
    deployment_id: int, 
    upload_file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    """
    [Proxy] 시각화된(Bounding Box가 그려진) 이미지를 반환합니다.
    Target BentoML: POST /predict/visual (BentoML 서비스 구현에 따라 경로 수정 필요)
    """
    # 1. 배포 정보 조회
    dep = db.query(Deployment).get(deployment_id)

    if not dep or not dep.container_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="배포 정보를 찾을 수 없거나 컨테이너가 실행 중이지 않습니다."
        )

    target_url = f"http://{serving_host(dep)}:3000/predict"
    
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

@router.post("/{deployment_id}/extract-sample")
async def extract_sample_proxy(
    deployment_id: int, 
    upload_file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    """
    [Proxy] 사용자가 업로드한 .npy 파일에서 샘플 데이터를 추출하여 반환합니다.
    Target BentoML: POST /utils/extract-sample
    """
    dep = db.query(Deployment).get(deployment_id)
    if not dep or not dep.container_id:
        raise HTTPException(status_code=404, detail="배포 컨테이너를 찾을 수 없습니다.")

    target_url = f"http://bento-serve-{deployment_id}:3000/utils/extract-sample"
    
    try:
        async with httpx.AsyncClient() as client:
            file_content = await upload_file.read()
            files = {'input_file': (upload_file.filename, file_content, 'application/octet-stream')}
            
            # BentoML 유틸리티 엔드포인트로 파일 전달
            response = await client.post(target_url, files=files, timeout=10.0)
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            
            return response.json()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"샘플 추출 실패: {str(e)}")