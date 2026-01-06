# docker 엔진과의 통신을 추상화 
import os
import docker
import asyncio
from typing import Optional, Dict, Any

class DockerProvider:
    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
            print(f"[DockerProvider] CONNECTED TO DOCKER (via {self.client.api.base_url})")
        except Exception as e:
            print(f"[DockerProvider] DOCKER CONNECTION FAILED: {e}")
            self.client = None
        
    def run_container(
        self,
        image: str,
        command: str,
        environment: Dict[str, str],
        network: str,        # 순서 주의: JobService에서 넘기는 순서와 맞춤
        volumes: Dict[str, Any],
        detach: bool = False # 기본값 설정
    ):
        if not self.client:
            raise RuntimeError("Docker client is not initialized")
        
        return self.client.containers.run(
            image=image,
            command=command,
            environment=environment,
            network=network, # 혹은 network_mode=network
            volumes=volumes,
            shm_size="8G",
            device_requests=[docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])],
            detach=detach,
        )

    def get_container(self, container_id: str):
        return self.client.containers.get(container_id)

    def run_serving_container(
        self,
        image: str,
        name: str,
        environment: Dict[str, str],
        port_mapping: Dict[int, int],
        network: str,
        volumes: Dict[str, Any], # 볼륨 매개변수 추가
        gpu_id: str = "0"
    ):
        """
        최종 서빙 컨테이너를 실행합니다. (공유 볼륨 연결 필수)
        """
        return self.client.containers.run(
            image=image,
            name=name,
            environment=environment,
            # 컨테이너 3000 포트를 호스트의 port_mapping[3000]으로 연결
            ports={'3000/tcp': port_mapping[3000]}, 
            network=network,
            volumes=volumes,  # 여기서 빌더가 저장한 모델 폴더를 읽습니다.
            detach=True,
            device_requests=[docker.types.DeviceRequest(count=1, capabilities=[['gpu']])] if gpu_id != "cpu" else [],
            restart_policy={"Name": "always"}
        )
    
    def run_builder_container(
        self,
        image: str,
        name: str,
        environment: Dict[str, str],
        volumes: Dict[str, Any],
        network: str
    ) -> bool:
        """
        빌더 전용 컨테이너를 실행하고 완료(0)될 때까지 대기합니다.
        """
        if not self.client:
            raise RuntimeError("Docker client is not initialized")

        try:
            print(f"[DockerProvider] Launching builder: {name}")
            container = self.client.containers.run(
                image=image,
                name=name,
                environment=environment,
                volumes=volumes,
                network=network,
                extra_hosts={'host.docker.internal': 'host-gateway'},
                detach=True  # 비동기 제어를 위해 detach로 시작
            )

            # 컨테이너가 끝날 때까지 대기 (wait)
            # result는 {'Error': None, 'StatusCode': 0} 형태입니다.
            result = container.wait()
            exit_code = result.get("StatusCode", 1)

            # 빌더 로그 출력 (디버깅용)
            logs = container.logs().decode("utf-8")
            if exit_code != 0:
                print(f"[DockerProvider] Builder failed (Exit {exit_code}):\n{logs}")
            else:
                print(f"[DockerProvider] Builder success.")

            # 일회성 빌더 컨테이너 삭제 (리소스 정리)
            container.remove()
            
            return exit_code == 0

        except Exception as e:
            print(f"[DockerProvider] Builder Error: {e}")
            return False
    
    def stream_container_logs(self, container_id: str):
        """
        지정된 컨테이너의 로그를 실시간으로 스트리밍합니다.
        """
        try:
            container = self.client.containers.get(container_id)
            for line in container.logs(stream=True, follow=True):
                yield f"data: {line.decode('utf-8')}\n\n"
    
        except Exception as e:
            yield f"data: [System Error] 로그를 가져오는 중 오류 발생: {str(e)}\n\n"

docker_provider = DockerProvider()