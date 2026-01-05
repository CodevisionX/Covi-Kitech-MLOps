from fastapi import APIRouter
from app.api.v1.endpoints import artifacts, experiments, jobs, projects, deployment

# v1 전용 통합 라우터 생성
api_router = APIRouter()

api_router.include_router(jobs.router, prefix="/jobs", tags=["Job"])
api_router.include_router(experiments.router, prefix="/experiments", tags=["Experiments"])
api_router.include_router(artifacts.router, prefix="/artifacts", tags=["Artifacts/S3"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(deployment.router, prefix="/deployments", tags=["Deployments"])