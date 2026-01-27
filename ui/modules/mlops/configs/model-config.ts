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
  requiredKeyword: string;
  parameters: ModelParameter[];
}

export const MODEL_CONFIGS: { [key: string]: ModelConfig } = {
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