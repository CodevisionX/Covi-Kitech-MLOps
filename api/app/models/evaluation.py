from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.core.constants import EvaluationStatus
from app.db.base_class import Base
from app.models.job import get_kst_now


class Evaluation(Base):
    """검출 모델 + 인식 모델 조합의 E2E 평가. 결과 지표와 예측은 MLflow run 에 남습니다."""
    __tablename__ = "evaluation"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False, index=True)
    name = Column(String(128), nullable=True)

    detection_job_id = Column(Integer, ForeignKey("job.id"), nullable=False, index=True)
    recognition_job_id = Column(Integer, ForeignKey("job.id"), nullable=False, index=True)
    dataset_version_id = Column(Integer, ForeignKey("dataset_version.id"), nullable=False, index=True)
    detection_job = relationship("Job", foreign_keys=[detection_job_id])
    recognition_job = relationship("Job", foreign_keys=[recognition_job_id])
    dataset_version = relationship("DatasetVersion")

    params = Column(JSON, default=dict)        # conf, iou, imgsz, max_det, padding
    status = Column(String, default=EvaluationStatus.PENDING.value, index=True)
    status_message = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    run_id = Column(String, nullable=True)
    experiment_id = Column(String, nullable=True)
    container_id = Column(String, nullable=True)
    metrics = Column(JSON, default=dict)
    summary = Column(JSON, default=dict)       # 슬롯/패널별 정확도, 오류 수

    created_at = Column(DateTime(timezone=True), default=get_kst_now)
    updated_at = Column(DateTime(timezone=True), default=get_kst_now, onupdate=get_kst_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)
