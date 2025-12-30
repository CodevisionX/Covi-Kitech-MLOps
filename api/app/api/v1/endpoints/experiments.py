import os
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from typing import List
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models.job import Job
from app.integrations.mlflow import mlflow_provider
from app.schemas.experiment import ExperimentResponse, RunResponse
import mlflow

router = APIRouter()

# [신규] 특정 프로젝트에 속한 MLflow 실험 목록 조회
@router.get("/project/{project_id}", response_model=List[ExperimentResponse])
async def get_experiments_by_project(project_id: int, db: Session = Depends(get_db)):
    """
    특정 프로젝트의 Job들이 사용하고 있는 중복 없는 MLflow 실험 목록을 가져옵니다.
    """
    try:
        # 1. DB에서 해당 프로젝트의 Job들이 가진 experiment_id 추출
        exp_ids = db.query(Job.experiment_id).filter(
            Job.project_id == project_id
        ).distinct().all()
        
        target_ids = [e[0] for e in exp_ids if e[0]]
        
        if not target_ids:
            return []

        # 2. MLflow에서 실험 정보 상세 조회
        all_exps = mlflow_provider.client.search_experiments()
        result = [
            ExperimentResponse(
                experiment_id=e.experiment_id,
                name=e.name,
                lifecycle_stage=e.lifecycle_stage
            ) for e in all_exps if e.experiment_id in target_ids
        ]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# [신규] 특정 Run의 상세 정보 조회 (상세 페이지용)
@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run_detail(run_id: str):
    """특정 Run의 모든 메타데이터, 파라미터, 메트릭을 가져옵니다."""
    try:
        run = mlflow_provider.get_run(run_id)
        return RunResponse(
            run_id=run.info.run_id,
            run_name=run.data.tags.get("mlflow.runName", "Unnamed"),
            status=run.info.status,
            start_time=run.info.start_time,
            end_time=run.info.end_time,
            metrics=run.data.metrics,
            params=run.data.params,
            tags=run.data.tags,
            artifact_uri=run.info.artifact_uri
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Run not found: {str(e)}")

# [유지/보합] 메트릭 히스토리 조회
@router.get("/{run_id}/metrics/history")
async def get_metrics_history(run_id: str):
    try:
        # YOLOv8 기준 주요 지표 매핑 (학습 스크립트의 로그 키와 일치해야 함)
        metric_keys = [
            "metrics/mAP50B", 
            "metrics/mAP50-95B", 
            "train/box_loss", 
            "train/cls_loss",
            "val/box_loss",
            "val/cls_loss"
        ]
        
        history_data = {}
        for key in metric_keys:
            try:
                history = mlflow_provider.client.get_metric_history(run_id, key)
                history_data[key] = [m.value for m in history]
            except:
                history_data[key] = []
        
        return history_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# [유지/보합] 아티팩트 미리보기
@router.get("/{run_id}/artifacts/preview")
async def get_artifact_preview(run_id: str, filename: str):
    try:
        cache_dir = os.path.abspath(f"./artifact_cache/{run_id}")
        os.makedirs(cache_dir, exist_ok=True)
        
        # 파일 경로 세팅 (S3에서 다운로드 시 하위 폴더 구조 유지)
        safe_filename = filename.replace("/", "_")
        local_path = os.path.join(cache_dir, safe_filename)

        if not os.path.exists(local_path):
            downloaded_path = mlflow.artifacts.download_artifacts(
                run_id=run_id, 
                artifact_path=filename,
                dst_path=cache_dir
            )
            # 폴더가 생성되며 다운로드될 경우 실제 파일 경로 재탐색
            if os.path.isdir(downloaded_path):
                # 보통 dst_path/filename 경로에 저장됨
                actual_file = os.path.join(downloaded_path, os.path.basename(filename))
                if os.path.exists(actual_file):
                    return FileResponse(actual_file)
            return FileResponse(downloaded_path)
            
        return FileResponse(local_path)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {str(e)}")