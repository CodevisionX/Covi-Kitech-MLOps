export type EvaluationStatus = 'PENDING' | 'DETECTING' | 'RECOGNIZING' | 'FINISHED' | 'FAILED';

export interface IEvaluationParams {
  conf: number;
  iou: number;
  imgsz: number;
  max_det: number;
  padding: number;
}

export const DEFAULT_EVALUATION_PARAMS: IEvaluationParams = {
  conf: 0.25, iou: 0.3, imgsz: 640, max_det: 20, padding: 0,
};

export interface IEvaluationCreate {
  project_id: number;
  detection_job_id: number;
  recognition_job_id: number;
  dataset_version_id: number;
  name?: string;
  params: IEvaluationParams;
}

export interface IEvaluation {
  id: number;
  project_id: number;
  name?: string | null;
  detection_job_id: number;
  recognition_job_id: number;
  dataset_version_id: number;
  params: IEvaluationParams;
  status: EvaluationStatus;
  status_message?: string | null;
  error_message?: string | null;
  run_id?: string | null;
  experiment_id?: string | null;
  metrics?: Record<string, number> | null;
  summary?: Record<string, any> | null;
  created_at: string;
  finished_at?: string | null;
}

/** predictions.csv 한 줄 */
export interface IEvaluationRow {
  image: string;
  panel: string;
  slot: string;
  panel_boxes: string;
  gt: string;
  pred: string;
  rec_score: string;
  det_conf: string;
  bbox: string;
  result: 'correct' | 'wrong' | 'panel_not_6' | 'unlabeled' | string;
}
