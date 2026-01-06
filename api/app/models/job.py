from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta, timezone
from app.db.base_class import Base
from app.core.constants import JobStatus

KST = timezone(timedelta(hours=9), 'KST')

def get_kst_now():
    return datetime.now(KST)

class Job(Base):
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default=JobStatus.PENDING.value, index=True)
    experiment_id = Column(String, index=True, nullable=False)

    # Project 연동
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    project = relationship("Project", back_populates="jobs")

    deployment = relationship("Deployment", back_populates="job", uselist=False)
    
    # 1. 필수 메타데이터 (모든 학습에 공통적으로 필요한 정보)
    model_variant = Column(String, nullable=False) # 예: yolov8n, resnet50
    dataset = Column(String, nullable=False)       # 예: bucket/path/to/data
    
    # 2. 가변 파라미터 (모델마다 달라질 수 있는 설정들)
    # 예: {"epochs": 100, "batch": 16, "lr": 0.01, "optimizer": "adam"}
    params = Column(JSON, default={}) 
    # 동적 태그 저장을 위한 JSON 필드
    tags = Column(JSON, default={})
    
    # 실행 관련 정보
    run_id = Column(String, nullable=True)       # MLflow Run ID
    container_id = Column(String, nullable=True) # Docker Container ID
    metrics = Column(JSON, default={})

    # 시간 및 에러 정보
    created_at = Column(DateTime(timezone=True), default=get_kst_now)
    updated_at = Column(DateTime(timezone=True), default=get_kst_now, onupdate=get_kst_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)