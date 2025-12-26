from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, timedelta, timezone
from app.db.base_class import Base

KST = timezone(timedelta(hours=9), 'KST')

def get_kst_now():
    return datetime.now(KST)

class TrainingJob(Base):
    __tablename__ = "training_jobs" # 명시적 선언이 자동 생성보다 우선함
    
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="PENDING")
    model_variant = Column(String)
    dataset = Column(String)
    epochs = Column(Integer)
    batch = Column(Integer)
    run_id = Column(String, nullable=True)
    container_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_kst_now)
    updated_at = Column(DateTime(timezone=True), default=get_kst_now, onupdate=get_kst_now)