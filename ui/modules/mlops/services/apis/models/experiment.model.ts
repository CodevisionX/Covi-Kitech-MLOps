export interface IExperiment {
  experiment_id: string;
  name: string;
  lifecycle_stage: string;
}

export interface IMLflowRun {
  run_id: string;
  run_name?: string;
  status: string;
  start_time: number;
  end_time?: number;
  metrics: Record<string, number>;
  params: Record<string, string>;
  tags: Record<string, string>;
  artifact_uri?: string;
}