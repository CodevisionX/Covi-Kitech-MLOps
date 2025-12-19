export interface ModelParameter {
  name: string;
  label: string;
  type: 'number' | 'select' | 'text';
  default: any;
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
      { name: 'epochs', label: 'Epochs', type: 'number', default: 100, min: 1 },
      { name: 'batch', label: 'Batch Size', type: 'select', options: [8, 16, 32, 64], default: 16 },
      { name: 'model_variant', label: 'Model Version', type: 'select', options: ['yolov8n', 'yolov8s', 'yolov8m'], default: 'yolov8n' }
    ]
  },
  'EfficientNet': {
    description: 'Image Classification',
    parameters: [
      { name: 'learning_rate', label: 'LR', type: 'number', default: 0.001 },
      { name: 'optimizer', label: 'Optimizer', type: 'select', options: ['Adam', 'SGD'], default: 'Adam' }
    ]
  }
};