import os
import threading
import time
import docker
import requests
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.deployment import Deployment
from app.models.job import Job
from app.core.constants import DeploymentStatus, JobStatus
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class ResourceManager:
    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
            print(f"[ResourceManager] CONNECTED TO DOCKER (via {self.client.api.base_url})")
        except Exception as e:
            print(f"[ResourceManager] DOCKER CONNECTION FAILED: {e}")
            self.client = None
        self.port_range = range(8001, 8100)
        self._port_lock = threading.Lock()
        self._reserved = {}  # 포트 -> 고른 시각. 컨테이너가 생기기 전 동시 요청이 같은 포트를 받지 않도록
        self.max_deployments_per_project = settings.MAX_DEPLOYMENTS_PER_PROJECT  # 사용자당 최대 배포 가능 개수 설정

    def check_project_quota(self, project_id: int) -> bool:
        """배포 시작 전에 특정 프로젝트가 배포 가능한 쿼터를 초과했는지 확인합니다."""
        with SessionLocal() as db:
            active_count = db.query(Deployment).filter(
                Deployment.project_id == project_id,
                Deployment.status == DeploymentStatus.RUNNING
            ).count()
            return active_count < self.max_deployments_per_project
    
    def find_available_port(self) -> int:
        """가용한 호스트 포트를 찾습니다.

        백엔드는 컨테이너 안에서 돌기 때문에 소켓 검사로는 호스트 포트 사용 여부를 알 수 없습니다.
        Docker 에 게시된 포트, 진행 중인 배포의 포트, 방금 고른 포트(동시 요청 대비)를 모두 피합니다.
        """
        active = [DeploymentStatus.PENDING, DeploymentStatus.REGISTERING, DeploymentStatus.BUILDING,
                  DeploymentStatus.CREATING, DeploymentStatus.RUNNING]
        with self._port_lock:
            with SessionLocal() as db:
                used = {d.port for d in db.query(Deployment).filter(Deployment.status.in_(active)).all() if d.port}
            if self.client:
                for c in self.client.containers.list(all=True):
                    for bindings in (c.attrs.get("HostConfig", {}).get("PortBindings") or {}).values():
                        for b in bindings or []:
                            if str(b.get("HostPort", "")).isdigit():
                                used.add(int(b["HostPort"]))
            now = time.monotonic()
            self._reserved = {p: t for p, t in self._reserved.items() if now - t < 300}
            used |= set(self._reserved)
            for port in self.port_range:
                if port not in used:
                    self._reserved[port] = now
                    return port
        raise Exception("가용 포트가 없습니다 (8001-8100).")

    def _check_app_health(self, port: int) -> bool:
        """BentoML 표준 헬스체크 엔드포인트를 확인합니다."""
        try:
            # BentoML 표준 헬스체크 경로: /livez (Liveness), /readyz (Readiness)
            response = requests.get(f"http://localhost:{port}/livez", timeout=2)
            return response.status_code == 200
        except Exception:
            return False
    
    def get_gpu_assignment(self):
        """학습 작업 유무에 따라 GPU 할당 전략을 결정합니다."""
        with SessionLocal() as db:
            # 현재 'RUNNING' 상태인 학습 작업(Job)이 있는지 확인
            is_training = db.query(Job).filter(Job.status == JobStatus.RUNNING).first()
        
        # 학습 중이면 배포는 CPU로 유도하여 자원 충돌 방지
        return "cpu" if is_training else "0"
    
    def sync_container_status(self):
        """
        1. Docker 컨테이너 상태 체크
        2. 내부 앱 헬스 체크 (HTTP)
        두 가지를 모두 통과해야 RUNNING 유지
        """
        with SessionLocal() as db:
            active_deployments = db.query(Deployment).filter(
                Deployment.status == DeploymentStatus.RUNNING
            ).all()

            for dep in active_deployments:
                # 1단계: Docker 컨테이너 존재 확인
                try:
                    container = self.client.containers.get(dep.container_id)
                    
                    if container.status != "running":
                        dep.status = DeploymentStatus.FAILED
                        dep.status_message = f"Docker container is {container.status}"
                        logger.warning(f"[Sync] Deployment {dep.id} container down.")
                        continue

                    # 2단계: 내부 앱 헬스 체크 (컨테이너는 떠 있는데 응답이 없는 경우)
                    if not self._check_app_health(dep.port):
                        dep.status = DeploymentStatus.FAILED
                        dep.status_message = "Container is running but App is unresponsive (Health Check Failed)"
                        logger.error(f"[Sync] Deployment {dep.id} application unhealthy.")
                
                except docker.errors.NotFound:
                    dep.status = DeploymentStatus.FAILED
                    dep.status_message = "Container not found on host"
                    logger.error(f"[Sync] Deployment {dep.id} container missing.")
                
                except Exception as e:
                    logger.error(f"[Sync] Error checking deployment {dep.id}: {e}")

            db.commit()
    
resource_manager = ResourceManager()