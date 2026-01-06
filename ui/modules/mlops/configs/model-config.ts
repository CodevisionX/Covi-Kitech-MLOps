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
  parameters: ModelParameter[];
}

export const MODEL_CONFIGS: { [key: string]: ModelConfig } = {
  'YOLOv8': {
    description: 'Real-time Object Detection',
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
        // [수정 완료] model_variant -> model_architecture 로 변경
        name: 'model_architecture', 
        label: 'Model Architecture', 
        type: 'select', 
        // 학습 코드에서 바로 사용할 수 있도록 확장자(.pt) 포함
        options: ['yolov8n.pt'], //, 'yolov8s.pt', 'yolov8m.pt'],
        default: 'yolov8n.pt',
        tooltip: '모델의 크기를 선택합니다. n(nano)은 매우 빠르고 가볍지만, m(medium)으로 갈수록 정확도가 높아지는 대신 연산량이 많아집니다.'
      }
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