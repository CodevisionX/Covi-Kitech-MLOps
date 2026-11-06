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
    E2E = "e2e"                 # 검출 + 인식을 이어 붙인 평가 전용 (패널/프레임 이미지 + 슬롯 정답)
    TIMESERIES = "timeseries"   # 시계열 (X.npy / y.npy, 분류·회귀)

    def __str__(self):
        return self.value


# 모델 종류 -> 학습에 쓰는 데이터셋 종류. 모든 모델은 등록된 데이터셋 버전으로만 학습합니다.
# 모델을 추가할 때는 여기와 job_service.get_training_runtime, UI 의 model-config 를 함께 맞춥니다.
MODEL_DATASET_TASKS = {
    "YOLO26": DatasetTask.DETECTION.value,
    "YOLOv8": DatasetTask.DETECTION.value,
    "PP-OCRv6": DatasetTask.RECOGNITION.value,
    "1D-CNN": DatasetTask.TIMESERIES.value,
}

# 종류별 모델 목록 (예: E2E 평가의 검출 모델 후보)
DETECTION_MODELS = {m for m, t in MODEL_DATASET_TASKS.items() if t == DatasetTask.DETECTION.value}
RECOGNITION_MODELS = {m for m, t in MODEL_DATASET_TASKS.items() if t == DatasetTask.RECOGNITION.value}

# MLflow pyfunc 로 기록되어 학습 이미지에서 바로 서빙하는 모델 (BentoML 빌드를 거치지 않음)
PYFUNC_SERVING_MODELS = set(MODEL_DATASET_TASKS)

# v1 에서 버킷 경로로 직접 학습하던 모델. 그때 만든 학습 기록은 BentoML 경로로 계속 보고 배포합니다.
LEGACY_MODELS = {"YOLOv8", "1D-CNN"}


def is_legacy_job(job) -> bool:
    """v1 방식(등록 데이터셋 없이 경로로 학습)으로 만든 기존 모델 학습 기록인지."""
    return (job.model_variant in LEGACY_MODELS and not job.dataset_version_id
            and (job.tags or {}).get("source") != "imported")


def is_pyfunc_job(job) -> bool:
    return job.model_variant in PYFUNC_SERVING_MODELS and not is_legacy_job(job)


class EvaluationStatus(str, Enum):
    PENDING = "PENDING"
    DETECTING = "DETECTING"       # 1단계: 검출 + 슬롯 Crop (YOLO26 이미지)
    RECOGNIZING = "RECOGNIZING"   # 2단계: 인식 + 채점 (PP-OCR 이미지)
    FINISHED = "FINISHED"
    FAILED = "FAILED"

    def __str__(self):
        return self.value
