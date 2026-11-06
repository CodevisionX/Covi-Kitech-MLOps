import asyncio
from contextlib import asynccontextmanager
from app.services.job_service import JobService
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.session import engine, SessionLocal
from app.db.base_class import Base

from app.models.project import Project 
from app.models.dataset import DatasetVersion  # noqa: F401 (create_all 대상 등록)
from app.models.evaluation import Evaluation  # noqa: F401
from app.integrations.s3 import s3_provider
from sqlalchemy import text
from sqlalchemy.orm import Session

def seed_db(db: Session):
    """
    초기 프로젝트 데이터가 없는 경우 기본 프로젝트를 생성합니다.
    """
    try:
        # 1. 프로젝트가 하나라도 있는지 확인 (혹은 특정 이름으로 확인)
        project_count = db.query(Project).count()
        
        if project_count == 0:
            print("Project table is empty. Seeding default project...")
            default_project = Project(
                name="algorithm",
                description="기본 프로젝트입니다."
            )
            db.add(default_project)
            db.commit()
            print("[+] Default project 'algorithm' created.")
        else:
            print(f"[*] Project table already has {project_count} projects. Skipping seed.")
    except Exception as e:
        print(f"[!] Seeding error: {e}")
        db.rollback()

# --- 1. Lifespan 관리 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    서버의 시작(Startup)과 종료(Shutdown) 시 실행될 로직을 정의합니다.
    """
    # [Startup] 1. DB 테이블 생성 (Alembic 도입 전까지 사용)
    Base.metadata.create_all(bind=engine)
    # create_all 은 기존 테이블에 열을 추가하지 않으므로 v2 에서 추가한 열은 직접 보강
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE job ADD COLUMN IF NOT EXISTS dataset_version_id INTEGER "
            "REFERENCES dataset_version(id)"))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_job_dataset_version_id ON job (dataset_version_id)"))
        conn.execute(text("ALTER TABLE deployment ADD COLUMN IF NOT EXISTS model_family VARCHAR"))
        conn.execute(text("ALTER TABLE job ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE"))

    # 브라우저가 데이터셋 버킷에 직접 업로드할 수 있도록 CORS 설정 (멱등)
    try:
        s3_provider.ensure_upload_cors(settings.DATASET_BUCKET_NAME)
    except Exception as e:
        print(f"[!] 데이터셋 버킷 CORS 설정 실패 (브라우저 업로드 불가, CLI 업로드는 가능): {e}")
    
    # 서버 재시작 시 큐 복구 로직
    # 단순히 process_queue()를 한 번 호출해주면, 대기 중인 작업이 있다면 실행됩니다.
    db = SessionLocal()
    try:
        seed_db(db) # 시딩 함수 호출
        
        # [Startup] 3. 서버 재시작 시 큐 복구 로직
        service = JobService()
        asyncio.create_task(service.process_queue())
    finally:
        db.close()

    yield
    # --- 서버 실행 중 ---

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

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    # 이 로그가 서버 터미널에 찍히면 어떤 데이터가 잘못되었는지 바로 알 수 있습니다.
    print(f"Validation Error: {exc.errors()}")
    body = await request.body()
    print(f"Sent Body: {body.decode('utf-8') if body else 'Empty'}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})