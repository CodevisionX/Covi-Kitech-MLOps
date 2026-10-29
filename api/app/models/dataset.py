from sqlalchemy import (BigInteger, Column, DateTime, ForeignKey, Integer, JSON, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import relationship

from app.core.constants import DatasetStatus
from app.db.base_class import Base
from app.models.job import get_kst_now


class DatasetVersion(Base):
    """데이터셋의 한 버전. READY 가 되면 저장 위치의 파일과 매니페스트는 바뀌지 않습니다."""
    __tablename__ = "dataset_version"
    __table_args__ = (UniqueConstraint("project_id", "name", "version", name="uq_dataset_version"),)

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False, index=True)
    project = relationship("Project")

    name = Column(String(64), nullable=False, index=True)
    version = Column(Integer, nullable=True)       # 검사 시작 시 부여, 실패하면 비움
    task = Column(String(32), nullable=False)      # detection | recognition
    description = Column(Text, nullable=True)
    status = Column(String(16), default=DatasetStatus.UPLOADING.value, index=True)

    staging_prefix = Column(String, nullable=False)  # 버킷 안 키 접두어: _staging/<uuid>/
    storage_path = Column(String, nullable=True)     # bucket/registered/p<프로젝트>/<이름>/v<N>

    manifest_sha256 = Column(String(64), nullable=True)
    file_count = Column(Integer, nullable=True)
    total_bytes = Column(BigInteger, nullable=True)
    stats = Column(JSON, default=dict)
    report = Column(JSON, default=dict)               # 검사 오류/경고
    error_message = Column(Text, nullable=True)
    container_id = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=get_kst_now)
    updated_at = Column(DateTime(timezone=True), default=get_kst_now, onupdate=get_kst_now)
    validated_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def data_path(self):
        """학습 작업에 넘기는 데이터 경로 (bucket/prefix)."""
        return f"{self.storage_path}/data" if self.storage_path else None
