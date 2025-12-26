import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.session import engine, SessionLocal
from app.db.base_class import Base
from app.services.TrainingService import training_service
from app.models.training import TrainingJob
from app.schemas.training import JobStatus


# --- 1. Lifespan 관리 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    서버의 시작(Startup)과 종료(Shutdown) 시 실행될 로직을 정의합니다.
    """
    # [Startup] 1. DB 테이블 생성 (Alembic 도입 전까지 사용)
    Base.metadata.create_all(bind=engine)
    
    # [Startup] 2. 백그라운드 학습 워커 가동
    worker_task = asyncio.create_task(training_service.run_worker())
    
    # [Startup] 3. 서버 재시작 시 DB에 남은 PENDING 작업들 큐에 복구
    with SessionLocal() as db:
        pending_jobs = db.query(TrainingJob).filter(
            TrainingJob.status == JobStatus.PENDING
        ).order_by(TrainingJob.created_at.asc()).all()
        
        for job in pending_jobs:
            await training_service.queue.put({"job_id": job.id})
        print(f"{len(pending_jobs)}개의 대기 중인 작업을 큐에 복구했습니다.")

    yield  # --- 서버 실행 중 ---

    # [Shutdown] 1. 실행 중인 워커 작업 취소 및 정리
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        print("백그라운드 워커가 안전하게 종료되었습니다.")

# --- 2. FastAPI 인스턴스 생성 ---
app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

# --- 3. CORS 미들웨어 설정 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 4. 라우터 통합 (Versioning) ---
app.include_router(api_router, prefix="/api/v1")

# --- 5. 헬스 체크 엔드포인트 ---
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy", "version": "v1.0.0"}