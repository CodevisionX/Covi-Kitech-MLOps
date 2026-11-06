import { IDeployment } from "./deployment.model";

export enum JobStatus {
  PENDING = 'PENDING',
  RUNNING = 'RUNNING',
  FINISHED = 'FINISHED',
  FAILED = 'FAILED',
  CANCELED = 'CANCELED',
  KILLED = 'KILLED'
}

export interface IJobCreate {
  project_id: number;
  // experiment_id: string;
  dataset: string;
  dataset_version_id?: number | null;
  model_variant: string;
  params: Record<string, any>; 
  tags: Record<string, any>;
}

export interface IJob {
  id: number;
  project_id: number;
  status: JobStatus;
  
  // JobBase 상속 필드
  model_variant: string;
  dataset: string;
  dataset_version_id?: number | null;
  params: Record<string, any>;
  tags: Record<string, any>;

  metrics?: Record<string, number> | null;
  /** 실행 중인 학습의 에폭 진행도 (완료 에폭 / 전체 에폭) */
  progress?: { epoch: number; total: number } | null;

  // 실행 정보
  run_id?: string | null;
  experiment_id: string;
  container_id?: string | null;
  deployment?: IDeployment;

  // 시간 정보 (JSON으로 넘어오면 string)
  created_at: string;
  updated_at?: string | null;
  finished_at?: string | null;
  started_at?: string | null;

  // 에러 정보
  error_message?: string | null; // [추가됨]
}

