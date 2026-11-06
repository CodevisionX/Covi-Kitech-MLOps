export interface ModelParameter {
  name: string;
  label: string;
  type: 'number' | 'select' | 'text';
  default: any;
  tooltip: string;
  min?: number | null;
  options?: any[];
  /** select 에 '직접 입력'을 둘 때 허용 범위 (정수) */
  custom?: { min: number; max: number; hint: string };
}

export interface ModelConfig {
  description: string;
  /** 이 종류로 등록(READY)된 데이터셋 버전에서만 학습 (백엔드 MODEL_DATASET_TASKS 와 같게 유지) */
  datasetTask: 'detection' | 'recognition' | 'timeseries';
  /** 학습 결과를 서빙/E2E 평가/배포 패키지에 쓸 수 있는 모델 */
  pyfunc?: boolean;
  /** 학습 이력에서 최고 모델을 고를 지표 (higher: 클수록 좋음) */
  bestMetric?: { key: string; label: string; higher: boolean };
  parameters: ModelParameter[];
}

export const MODEL_CONFIGS: { [key: string]: ModelConfig } = {
  'YOLO26': {
    description: '패널 숫자 영역 검출 (YOLO26n)',
    datasetTask: 'detection',
    pyfunc: true,
    bestMetric: { key: 'best_val/mAP50-95', label: 'Val mAP50-95', higher: true },
    parameters: [
      { name: 'epochs', label: 'Epochs', type: 'number', default: 100, min: 1,
        tooltip: '학습 반복 횟수입니다. Validation 성능이 patience 에폭 동안 오르지 않으면 일찍 멈춥니다.' },
      { name: 'batch', label: 'Batch Size', type: 'select', options: [2, 4, 8, 16, 32, 64, 128], default: 8,
        custom: { min: 1, max: 256, hint: '1~256, 8의 배수 권장' },
        tooltip: '한 번에 학습할 이미지 수입니다. 클수록 빠르지만 GPU 메모리를 많이 씁니다. 학습이 메모리 부족으로 멈추면 줄이세요.' },
      { name: 'imgsz', label: 'Image Size', type: 'select', options: [640, 960, 1280], default: 640,
        tooltip: '학습/추론 입력 크기입니다. 현장 운영 코드는 640을 씁니다. 바꾸면 평가와 현장 설정도 같이 바꿔야 합니다.' },
      { name: 'patience', label: 'Patience', type: 'number', default: 20, min: 1,
        tooltip: 'Validation 성능이 이 에폭 수만큼 좋아지지 않으면 학습을 멈춥니다.' },
      { name: 'seed', label: 'Seed', type: 'number', default: 42, min: 0,
        tooltip: '같은 값이면 같은 데이터로 같은 결과를 재현합니다.' },
    ]
  },
  'PP-OCRv6': {
    description: '숫자 인식 (PP-OCRv6 medium)',
    datasetTask: 'recognition',
    pyfunc: true,
    bestMetric: { key: 'best_val/acc', label: 'Val 정확도', higher: true },
    parameters: [
      { name: 'epochs', label: 'Epochs', type: 'number', default: 50, min: 1,
        tooltip: '학습 반복 횟수입니다. Validation 정확도가 가장 높은 체크포인트를 씁니다.' },
      { name: 'batch', label: 'Batch Size', type: 'select', options: [8, 16, 32, 64, 128, 256], default: 32,
        custom: { min: 1, max: 512, hint: '1~512, 8의 배수 권장' },
        tooltip: '한 번에 학습할 이미지 수입니다. 클수록 빠르지만 GPU 메모리를 많이 씁니다. 학습이 메모리 부족으로 멈추면 줄이세요.' },
      { name: 'learning_rate', label: 'Learning Rate', type: 'number', default: 0.0001,
        tooltip: '사전학습 모델을 미세 조정하므로 작은 값(1e-4 근처)을 권장합니다.' },
      { name: 'max_text_length', label: 'Max Text Length', type: 'number', default: 8, min: 1,
        tooltip: '한 슬롯에서 읽을 최대 글자 수입니다.' },
      { name: 'eval_batch_step', label: 'Eval Step', type: 'number', default: 50, min: 1,
        tooltip: '몇 step 마다 Validation 평가를 할지 정합니다.' },
    ]
  },
  'YOLOv8': {
    description: '검출 (YOLOv8n, YOLO26과 같은 방식으로 학습·평가)',
    datasetTask: 'detection',
    pyfunc: true,
    bestMetric: { key: 'best_val/mAP50-95', label: 'Val mAP50-95', higher: true },
    parameters: [
      { name: 'epochs', label: 'Epochs', type: 'number', default: 100, min: 1,
        tooltip: '학습 반복 횟수입니다. Validation 성능이 patience 에폭 동안 오르지 않으면 일찍 멈춥니다.' },
      { name: 'batch', label: 'Batch Size', type: 'select', options: [2, 4, 8, 16, 32, 64, 128], default: 8,
        custom: { min: 1, max: 256, hint: '1~256, 8의 배수 권장' },
        tooltip: '한 번에 학습할 이미지 수입니다. 클수록 빠르지만 GPU 메모리를 많이 씁니다. 학습이 메모리 부족으로 멈추면 줄이세요.' },
      { name: 'imgsz', label: 'Image Size', type: 'select', options: [640, 960, 1280], default: 640,
        tooltip: '학습/추론 입력 크기입니다.' },
      { name: 'patience', label: 'Patience', type: 'number', default: 20, min: 1,
        tooltip: 'Validation 성능이 이 에폭 수만큼 좋아지지 않으면 학습을 멈춥니다.' },
      { name: 'seed', label: 'Seed', type: 'number', default: 42, min: 0,
        tooltip: '같은 값이면 같은 데이터로 같은 결과를 재현합니다.' },
    ]
  },
  '1D-CNN': {
    description: '시계열 분류·회귀 (1D-CNN)',
    datasetTask: 'timeseries',
    pyfunc: true,
    // 분류·회귀 모두 있는 지표로 비교 (낮을수록 좋음)
    bestMetric: { key: 'best_val/loss', label: 'Val Loss', higher: false },
    parameters: [
      { name: 'epochs', label: 'Epochs', type: 'number', default: 50, min: 1,
        tooltip: '학습 반복 횟수입니다. Validation 기준(분류: 정확도, 회귀: 손실)이 가장 좋은 에폭을 씁니다.' },
      { name: 'batch', label: 'Batch Size', type: 'select', options: [8, 16, 32, 64, 128, 256, 512], default: 32,
        custom: { min: 1, max: 1024, hint: '1~1024, 8의 배수 권장' },
        tooltip: '한 번에 학습할 샘플 수입니다.' },
      { name: 'learning_rate', label: 'Learning Rate', type: 'number', default: 0.001,
        tooltip: '너무 크면 학습이 불안정하고, 너무 작으면 느립니다.' },
      { name: 'patience', label: 'Patience', type: 'number', default: 0, min: 0,
        tooltip: 'Validation 기준이 이 에폭 수만큼 좋아지지 않으면 멈춥니다. 0 이면 끝까지 학습합니다.' },
      { name: 'seed', label: 'Seed', type: 'number', default: 42, min: 0,
        tooltip: '같은 값이면 같은 데이터로 같은 결과를 재현합니다.' },
    ]
  },

  // 'EfficientNet': {
  //   description: 'Image Classification',
  //   parameters: [
  //     { 
  //       name: 'learning_rate', 
  //       label: 'Learning Rate', 
  //       type: 'number', 
  //       default: 0.001,
  //       tooltip: '모델이 학습할 때 가중치를 얼마나 큰 폭으로 업데이트할지 결정합니다. 너무 크면 학습이 불안정하고, 너무 작으면 학습이 지나치게 느려집니다.'
  //     },
  //     { 
  //       name: 'optimizer', 
  //       label: 'Optimizer', 
  //       type: 'select', 
  //       options: ['Adam', 'SGD'], 
  //       default: 'Adam',
  //       tooltip: '학습을 최적화하는 알고리즘입니다. Adam은 대부분의 상황에서 안정적인 성능을 보여 비전문가에게 추천합니다.'
  //     }
  //   ]
  // }
};

/** 모델 종류 -> 데이터셋 종류 (모르는 모델은 undefined) */
export function modelTask(variant: string | null | undefined): string | undefined {
  return variant ? MODEL_CONFIGS[variant]?.datasetTask : undefined;
}

export function isDetectionModel(variant: string | null | undefined): boolean {
  return modelTask(variant) === 'detection';
}

export function modelsForTask(task: string): string[] {
  return Object.keys(MODEL_CONFIGS).filter(k => MODEL_CONFIGS[k].datasetTask === task);
}

/** 학습 결과 요약(best_val/*, test/*)에 쓰는 지표 이름 */
export const METRIC_LABELS: Record<string, string> = {
  'mAP50': 'mAP@0.5',
  'mAP50-95': 'mAP@0.5:0.95',
  'precision': 'Precision',
  'recall': 'Recall',
  'acc': '정확도',
  'norm_edit_dis': '정규화 편집 유사도',
  'loss': 'Loss',
  'f1': 'F1 (macro)',
  'mae': 'MAE',
  'rmse': 'RMSE',
  'r2': 'R²',
};

/** 화면에 보여 줄 종류 순서와 이름 (작업 순서: 검출 → 인식 → 시계열) */
export const TASK_ORDER = ['detection', 'recognition', 'timeseries'];
export const TASK_NAMES: Record<string, string> = { detection: '검출', recognition: '인식', timeseries: '시계열' };

/** 종류 순서, 같은 종류 안에서는 MODEL_CONFIGS 순서로 정렬한 모델 목록 (모르는 모델은 맨 뒤) */
export function sortModels(variants: string[]): string[] {
  const keys = Object.keys(MODEL_CONFIGS);
  const rank = (v: string) => {
    const t = TASK_ORDER.indexOf(modelTask(v) ?? '');
    return (t < 0 ? TASK_ORDER.length : t) * 100 + (keys.includes(v) ? keys.indexOf(v) : 99);
  };
  return [...variants].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

/** v1 방식(등록 데이터셋 없이 버킷 경로로 학습)으로 만든 기존 모델 학습 기록 (BentoML 경로로 보고 배포) */
export const LEGACY_MODELS = ['YOLOv8', '1D-CNN'];
export function isLegacyJob(job: { model_variant: string; dataset_version_id?: number | null; tags?: Record<string, any> }): boolean {
  return LEGACY_MODELS.includes(job.model_variant) && !job.dataset_version_id && job.tags?.['source'] !== 'imported';
}
