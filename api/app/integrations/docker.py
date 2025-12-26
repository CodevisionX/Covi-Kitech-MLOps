# docker 엔진과의 통신을 추상화 
import docker
from typing import Optional, Dict, Any

class DockerProvider:
    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as e:
            print(f"Docker connection failed: {e}")
            self.client = None
        
    def run_container(
        self,
        image: str,
        command: str,
        environment: Dict[str, str],
        volumes: Dict[str, Any],
        network: str      
    ):
        if not self.client:
            raise RuntimeError("Docker client is not initialized")
        return self.client.containers.run(
            image=image,
            command=command,
            environment=environment,
            volumes=volumes,
            network=network,
            shm_size="8G",
            device_requests=[docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])],
            detach=True
        )

    def get_container(self, container_id: str):
        return self.client.containers.get(container_id)

docker_provider = DockerProvider()