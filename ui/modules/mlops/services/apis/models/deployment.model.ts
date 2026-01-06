export enum DeploymentStatus {
  PENDING = 'PENDING',
  REGISTERING = 'REGISTERING',
  BUILDING = 'BUILDING',
  CREATING = 'CREATING',
  RUNNING = 'RUNNING',
  STOPPED = 'STOPPED',
  CANCELED = 'CANCELED',
  FAILED = 'FAILED'
}

export interface IDeploymentBase {
  project_id: number;
  model_name: string;
  model_version?: number;
  run_id: string;
  job_id?: number;
}

export interface IDeploymentCreate extends IDeploymentBase {}

export interface IDeployment extends IDeploymentBase {
  id: number;
  status: DeploymentStatus;
  job_id?: number;
  status_message?: string;
  container_id?: string;
  port?: number;
  endpoint_url?: string;
  created_at: string;
  updated_at?: string;
}