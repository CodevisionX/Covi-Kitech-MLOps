export interface ModelParameter {
  name: string;
  label: string;
  type: 'number' | 'select' | 'text';
  default: any;
  tooltip: string;
  min?: number | null;
  options?: any[];
}

export interface ModelConfig {
  description: string;
  /** 기존 모델: 버킷 경로에 이 단어가 있어야 학습 가능 */
  requiredKeyword: string;
  /** 신규 모델: 이 종류로 등록(READY)된 데이터셋 버전에서만 학습 */
  datasetTask?: 'detection' | 'recognition';
  /** 학습 결과를 서빙/E2E 평가/배포 패키지에 쓸 수 있는 모델 */
  pyfunc?: boolean;
  /** 학습 이력에서 최고 모델을 고를 지표 (higher: 클수록 좋음) */
  bestMetric?: { key: string; label: string; higher: boolean };
  parameters: ModelParameter[];
}

export const MODEL_CONFIGS: { [key: string]: ModelConfig } = {
  'YOLO26': {
    description: '패널 숫자 영역 검출 (YOLO26n)',
    requiredKeyword: '',
    datasetTask: 'detection',
    pyfunc: true,
    bestMetric: { key: 'best_val/mAP50-95', label: 'Val mAP50-95', higher: true },
    parameters: [
      { name: 'epochs', label: 'Epochs', type: 'number', default: 100, min: 1,
        tooltip: '학습 반복 횟수입니다. Validation 성능이 patience 에폭 동안 오르지 않으면 일찍 멈춥니다.' },
      { name: 'batch', label: 'Batch Size', type: 'select', options: [4, 8, 16, 32], default: 8,
        tooltip: '한 번에 학습할 이미지 수입니다. GPU 메모리가 부족하면 줄이세요.' },
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
    requiredKeyword: '',
    datasetTask: 'recognition',
    pyfunc: true,
    bestMetric: { key: 'best_val/acc', label: 'Val 정확도', higher: true },
    parameters: [
      { name: 'epochs', label: 'Epochs', type: 'number', default: 50, min: 1,
        tooltip: '학습 반복 횟수입니다. Validation 정확도가 가장 높은 체크포인트를 씁니다.' },
      { name: 'batch', label: 'Batch Size', type: 'select', options: [16, 32, 64], default: 32,
        tooltip: '한 번에 학습할 이미지 수입니다. GPU 메모리가 부족하면 줄이세요.' },
      { name: 'learning_rate', label: 'Learning Rate', type: 'number', default: 0.0001,
        tooltip: '사전학습 모델을 미세 조정하므로 작은 값(1e-4 근처)을 권장합니다.' },
      { name: 'max_text_length', label: 'Max Text Length', type: 'number', default: 8, min: 1,
        tooltip: '한 슬롯에서 읽을 최대 글자 수입니다.' },
      { name: 'eval_batch_step', label: 'Eval Step', type: 'number', default: 50, min: 1,
        tooltip: '몇 step 마다 Validation 평가를 할지 정합니다.' },
    ]
  },
  'YOLOv8': {
    description: 'Real-time Object Detection',
    requiredKeyword: 'yolo',
    parameters: [
      { 
        name: 'epochs', 
        label: 'Epochs', 
        type: 'number', 
        default: 100, 
        min: 1, 
        tooltip: '전체 데이터셋을 몇 번 반복해서 학습할지 결정합니다. 숫자가 높을수록 성능이 좋아질 수 있지만 시간이 오래 걸립니다.' 
      },
      { 
        name: 'batch', 
        label: 'Batch Size', 
        type: 'select', 
        options: [8, 16, 32, 64], 
        default: 16, 
        tooltip: '한 번의 계산에 사용할 데이터의 묶음 크기입니다. 컴퓨터의 메모리(GPU) 성능에 맞춰 조절해야 합니다.' 
      },
      { 
        name: 'model_architecture', 
        label: 'Model Architecture', 
        type: 'select', 
        options: ['yolov8n.pt'], //, 'yolov8s.pt', 'yolov8m.pt'],
        default: 'yolov8n.pt',
        tooltip: '모델의 크기를 선택합니다. n(nano)은 매우 빠르고 가볍지만, m(medium)으로 갈수록 정확도가 높아지는 대신 연산량이 많아집니다.'
      }
    ]
  },
  '1D-CNN': {
    description: 'Sensor Data Analytics',
    requiredKeyword: '1d-cnn',
    parameters: [
      { 
        name: 'epochs', 
        label: 'Epochs', 
        type: 'number', 
        default: 50, 
        min: 1, 
        tooltip: '학습 반복 횟수입니다. 센서 데이터는 보통 30~100회 사이에서 안정적인 성능을 보입니다.' 
      },
      { 
        name: 'batch', 
        label: 'Batch Size', 
        type: 'select', 
        options: [16, 32, 64, 128], 
        default: 32, 
        tooltip: '학습 시 한 번에 처리할 데이터의 양입니다. 숫자가 작을수록 세밀하게 학습하지만 시간이 오래 걸립니다.' 
      },
      { 
        name: 'learning_rate', 
        label: 'Learning Rate', 
        type: 'number', 
        default: 0.001, 
        tooltip: '모델이 정답을 찾아가는 속도입니다. 너무 크면 학습이 불안정하고, 너무 작으면 학습 속도가 매우 느려집니다.' 
      },
      // { 
      //   name: 'window_size', 
      //   label: 'Window Size', 
      //   type: 'number', 
      //   default: 20, 
      //   min: 1,
      //   tooltip: '시계열 데이터를 얼마나 긴 단위로 묶어서 분석할지 결정합니다. 전처리 시 설정한 값과 일치해야 합니다.' 
      // },
      // { 
      //   name: 'model_architecture', 
      //   label: 'Model Architecture', 
      //   type: 'select', 
      //   options: ['1D-CNN-Standard', '1D-CNN-Deep'], 
      //   default: '1D-CNN-Standard',
      //   tooltip: '모델의 깊이를 선택합니다. 데이터가 복잡할수록 Deep 모델이 유리할 수 있습니다.'
      // }
    ]

  }

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