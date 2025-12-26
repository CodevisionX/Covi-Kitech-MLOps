export type ModelVariant = 'YOLOv8' | 'EfficientNet' | string; 

export interface ITrainRequest {
  model_variant: ModelVariant;
  dataset: string;
  epochs: number;
  batch: number;
  // [확장 포인트] 모델별로 추가적인 파라미터가 생길 경우를 대비
  extra_params?: Record<string, any>; 
}

// 2. 서버 응답 및 전체 정보를 위한 스키마
export interface ITrainingJob {
  id: number;
  status: 'PENDING' | 'RUNNING' | 'FINISHED' | 'FAILED' | 'CANCELLED';
  model_variant: string;
  dataset: string;
  epochs: number;
  batch: number;
  run_id?: string;       // 없을 수도 있으므로 Optional
  container_id?: string; // 없을 수도 있으므로 Optional
  mlflow_url: string;
  created_at: string;
  updated_at: string;
}

// 3. API 응답 전용 (보통 TrainingJob과 유사하지만 확장성을 위해 분리)
export interface IJobResponse extends ITrainingJob {}