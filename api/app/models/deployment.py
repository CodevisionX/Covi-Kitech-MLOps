from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum as SqlEnum
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from datetime import datetime, timezone, timedelta
from app.core.constants import DeploymentStatus

KST = timezone(timedelta(hours=9), 'KST')

class Deployment(Base):
    __tablename__ = "deployment"

    id = Column(Integer, primary_key=True, index=True)
    
    # Project와 연결 (필수)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    project = relationship("Project")

    # Job과 연결 (선택: 어떤 학습 결과인지 추적용)
    # 학습 없이 외부 모델을 등록할 수도 있으므로 nullable=True 권장
    job_id = Column(Integer, ForeignKey("job.id"), nullable=True)
    job = relationship("Job", back_populates="deployment")

    # MLflow 관련 정보
    model_name = Column(String, nullable=False)      # Registry 등록명
    model_version = Column(Integer, nullable=True)   # Registry 버전
    run_id = Column(String, nullable=False)          # MLflow Run ID (Lineage)

    # 배포 인프라 정보
    status = Column(
        SqlEnum(DeploymentStatus), 
        default=DeploymentStatus.PENDING,
        nullable=False
    )
    endpoint_url = Column(String, nullable=True)     # http://localhost:8001/predict/visual
    container_id = Column(String, nullable=True)     # 실행된 Docker ID
    port = Column(Integer, nullable=True)            # 할당된 포트

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(KST))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(KST))

    status_message = Column(Text, nullable=True)  # "Container creating..." 등의 상세 로그
    error_msg = Column(Text, nullable=True)       # FAILED 시 에러 원인 기록