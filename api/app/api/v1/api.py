from fastapi import APIRouter
from app.api.v1.endpoints import training

# v1 전용 통합 라우터 생성
api_router = APIRouter()

api_router.include_router(training.router, prefix="/training", tags=["Training"])
api_router.include_router(experiments.router, prefix="/experiments", tags=["Experiments"])
api_router.include_router(artifacts.router, prefix="/artifacts", tags=["Artifacts/S3"])