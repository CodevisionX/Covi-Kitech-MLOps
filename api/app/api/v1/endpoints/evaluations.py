# E2E 평가 (검출 모델 + 인식 모델) 와 배포 패키지
import shutil
from typing import List, Optional

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.db.dependencies import get_db
from app.schemas.evaluation import EvaluationCreate, EvaluationReport, EvaluationResponse
from app.services.evaluation_service import evaluation_service

router = APIRouter()


@router.post("", response_model=EvaluationResponse, status_code=status.HTTP_201_CREATED)
async def create_evaluation(body: EvaluationCreate, db: Session = Depends(get_db)):
    """완료된 YOLO26 학습과 PP-OCRv6 학습을 골라, 등록된 e2e 데이터셋으로 슬롯 단위 평가를 실행합니다."""
    return await evaluation_service.create(db, body)


@router.get("", response_model=List[EvaluationResponse])
def list_evaluations(project_id: Optional[int] = None, db: Session = Depends(get_db)):
    return evaluation_service.list(db, project_id)


@router.get("/{evaluation_id}", response_model=EvaluationResponse)
def get_evaluation(evaluation_id: int, db: Session = Depends(get_db)):
    return evaluation_service.get(db, evaluation_id)


@router.get("/{evaluation_id}/logs", response_class=PlainTextResponse)
def get_logs(evaluation_id: int, db: Session = Depends(get_db)):
    return evaluation_service.read_log(evaluation_service.get(db, evaluation_id))


@router.get("/{evaluation_id}/predictions")
def get_predictions(evaluation_id: int, db: Session = Depends(get_db)):
    """슬롯별 정답·예측 CSV (image, panel, slot, gt, pred, rec_score, det_conf, bbox, result)."""
    ev = evaluation_service.get(db, evaluation_id)
    return Response(evaluation_service.predictions_csv(ev), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="e2e_eval{ev.id}_predictions.csv"'})


@router.get("/{evaluation_id}/package")
def download_package(evaluation_id: int, db: Session = Depends(get_db)):
    """고객 현장 폴더 구조(models/detection, models/recognition)의 배포 zip."""
    ev = evaluation_service.get(db, evaluation_id)
    path = evaluation_service.build_package(db, ev)
    name = f"models_e2e{ev.id}_det{ev.detection_job_id}_rec{ev.recognition_job_id}.zip"
    return FileResponse(path, media_type="application/zip", filename=name,
                        background=BackgroundTask(shutil.rmtree, path.parent, True))


@router.delete("/{evaluation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evaluation(evaluation_id: int, db: Session = Depends(get_db)):
    """평가 기록을 지웁니다 (실행 중이면 중단). MLflow run 은 남습니다."""
    await evaluation_service.delete(db, evaluation_service.get(db, evaluation_id))


@router.post("/{evaluation_id}/report", include_in_schema=False)
async def report(evaluation_id: int, body: EvaluationReport, db: Session = Depends(get_db)):
    """[웹훅] 평가 컨테이너가 단계 결과를 보고합니다."""
    await evaluation_service.report(db, evaluation_service.get(db, evaluation_id), body)
    return {"ok": True}
