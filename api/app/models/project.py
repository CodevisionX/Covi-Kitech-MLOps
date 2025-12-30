from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, timezone
from app.db.base_class import Base

KST = timezone(timedelta(hours=9), 'KST')

def get_kst_now():
    return datetime.now(KST)

class Project(Base):
    __tablename__ = "project"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_kst_now)
    
    # 관계 설정: 하나의 프로젝트는 여러 개의 Job을 가짐
    jobs = relationship("Job", back_populates="project")