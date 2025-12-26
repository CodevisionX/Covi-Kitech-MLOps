export interface IExperiment {
  experiment_id: string;
  name: string;
  lifecycle_stage: string;
}

export interface IMLflowRun {
  run_id: string;
  run_name: string;
  status: string;
  metrics: any;
  params: any;
  tags?: {
    container_id?: string;
    [key: string]: any; // 다른 커스텀 태그들도 허용
  };
}