# MLflow 조회 및 메트릭 관리
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from typing import List
from app.integrations.mlflow import mlflow_provider
from app.schemas.experiment import ExperimentResponse, RunResponse
import mlflow
from app.integrations.mlflow import mlflow_provider

router = APIRouter()

@router.get("/", response_model=List[ExperimentResponse])
async def get_experiments():
    """모든 MLflow 실험 목록을 가져옵니다."""
    try:
        exps = mlflow_provider.client.search_experiments()
        return [
            ExperimentResponse(
                experiment_id=e.experiment_id,
                name=e.name,
                lifecycle_stage=e.lifecycle_stage
            ) for e in exps
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MLflow Error: {str(e)}")

@router.get("/{experiment_id}/runs", response_model=List[RunResponse])
async def get_runs(experiment_id: str):
    """특정 실험에 속한 모든 Run(실행) 항목을 가져옵니다."""
    try:
        runs = mlflow_provider.client.search_runs(
            experiment_ids=[experiment_id],
            order_by=["attributes.start_time DESC"]
        )
        return [
            RunResponse(
                run_id=run.info.run_id,
                run_name=run.data.tags.get("mlflow.runName", "Unnamed"),
                status=run.info.status,
                start_time=run.info.start_time,
                metrics=run.data.metrics,
                params=run.data.params
            ) for run in runs
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{run_id}/metrics/history")
async def get_metrics_history(run_id: str):
    """특정 Run의 메트릭 변화 이력을 차트용 데이터로 가져옵니다."""
    try:
        # 프론트엔드 키와 MLflow 메트릭 키 매핑
        metric_mapping = {
            "metrics.mAP50(B)": "metrics/mAP50B",
            "metrics.mAP50-95(B)": "metrics/mAP50-95B",
            "train.box_loss": "train/box_loss",
            "train.cls_loss": "train/cls_loss"
        }
        history_data = {}

        for frontend_key, mlflow_key in metric_mapping.items():
            try:
                # MLflow에서 해당 지표의 전체 이력(Step별 값) 추출
                history = mlflow_provider.client.get_metric_history(run_id, mlflow_key)
                history_data[frontend_key] = [m.value for m in history]
            except Exception:
                history_data[frontend_key] = []
        
        return history_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/{run_id}/artifacts/preview")
async def get_artifact_preview(run_id: str, filename: str = "val_batch0_labels.jpg"):
    """MLflow에 저장된 아티팩트(이미지)를 로컬 캐시 후 반환합니다."""
    try:
        cache_dir = f"./artifact_cache/{run_id}"
        local_path = os.path.join(cache_dir, filename)

        # 1. 캐시 확인
        if os.path.exists(local_path):
            return FileResponse(local_path)
        
        # 2. 캐시 없으면 MLflow에서 다운로드
        downloaded_path = mlflow.artifacts.download_artifacts(
            run_id=run_id, 
            artifact_path=filename,
            dst_path=cache_dir
        )
        return FileResponse(downloaded_path)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"아티팩트 로드 실패: {str(e)}")