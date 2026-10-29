from enum import Enum

class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    KILLED = "KILLED"

    def __str__(self):
        return self.value

class DeploymentStatus(str, Enum):
    # 1. 초기 단계
    PENDING = "PENDING"           # 배포 요청 접수 (초기 상태)
    
    # 2. 진행 단계
    REGISTERING = "REGISTERING"   # MLflow 모델 등록 진행 중
    BUILDING = "BUILDING"     # BentoML 이미지를 빌드하는 단계 추가
    CREATING = "CREATING"         # Docker 컨테이너 생성 및 실행 중
    
    # 3. 완료 및 종료 단계
    RUNNING = "RUNNING"           # 배포 완료 및 정상 서비스 중 (최종 성공)
    STOPPED = "STOPPED"           # 서비스 중인 모델을 수동 중단 (리소스 반납)
    
    # 4. 실패 및 취소 단계
    CANCELED = "CANCELED"         # 배포 중 사용자 취소 (리소스 정리 완료)
    FAILED = "FAILED"             # 오류 발생으로 인한 실패

    def __str__(self):
        return self.value

class DatasetStatus(str, Enum):
    UPLOADING = "UPLOADING"     # 임시 영역(_staging)에 업로드 중
    VALIDATING = "VALIDATING"   # 검사 작업 실행 중
    READY = "READY"             # 검사 통과, 등록 완료(변경 불가)
    FAILED = "FAILED"           # 검사 실패 (임시 영역은 남아 있어 고쳐서 다시 검사 가능)

    def __str__(self):
        return self.value


class DatasetTask(str, Enum):
    DETECTION = "detection"
    RECOGNITION = "recognition"

    def __str__(self):
        return self.value


# 등록된 데이터셋 버전으로만 학습하는 모델과 그 데이터셋 종류
MODEL_DATASET_TASKS = {
    "YOLO26": DatasetTask.DETECTION.value,
    "PP-OCRv6": DatasetTask.RECOGNITION.value,
}
