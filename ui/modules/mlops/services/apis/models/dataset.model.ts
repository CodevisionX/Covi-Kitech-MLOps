export type DatasetTask = 'detection' | 'recognition' | 'e2e' | 'timeseries';
export type DatasetStatus = 'UPLOADING' | 'VALIDATING' | 'READY' | 'FAILED';

export interface IDatasetVersion {
  id: number;
  project_id: number;
  name: string;
  version?: number | null;
  task: DatasetTask;
  description?: string | null;
  status: DatasetStatus;
  staging_prefix: string;
  storage_path?: string | null;
  data_path?: string | null;
  manifest_sha256?: string | null;
  file_count?: number | null;
  total_bytes?: number | null;
  stats?: Record<string, any> | null;
  report?: { errors?: string[]; warnings?: string[]; n_errors?: number; n_warnings?: number;[k: string]: any } | null;
  error_message?: string | null;
  created_at: string;
  updated_at?: string | null;
  validated_at?: string | null;
}

export interface IUploadSession extends IDatasetVersion {
  staging_uri: string;
  s3_endpoint: string;
  cli_example: string;
}

export interface IDatasetUploadCreate {
  project_id: number;
  name: string;
  task: DatasetTask;
  description?: string;
}

export interface IPresignedFile {
  path: string;
  method: 'PUT' | 'MULTIPART';
  url?: string;
  upload_id?: string;
  part_size?: number;
  parts?: { part_number: number; url: string }[];
}

export interface IPresignResponse {
  expires_in: number;
  files: IPresignedFile[];
}

export const DATASET_TASK_LABELS: Record<DatasetTask, string> = {
  detection: '검출 (YOLO26 · YOLOv8 학습용)',
  recognition: '인식 (PP-OCRv6 학습용)',
  e2e: 'E2E 평가용',
  timeseries: '시계열 (1D-CNN 학습용)',
};
