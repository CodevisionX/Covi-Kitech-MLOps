import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { HttpClient } from '@angular/common/http';
import { map, Observable } from 'rxjs';

export interface Experiment {
  experiment_id: string;
  name: string;
  lifecycle_stage: string;
}

export interface MLflowRun {
  run_id: string;
  run_name: string;
  status: string;
  start_time: number;
  end_time: number;
  metrics: any;
  params: any;
  tags: any;
}

@Injectable({
  providedIn: 'root',
})
export class Api {
  
  private http = inject(HttpClient);
  private apiUrl = environment.apiUrl;
  
  // --- [MinIO 관련] ---
  getBuckets(): Observable<{ datasets: string[] }> {
    return this.http.get<{ datasets: string[] }>(`${this.apiUrl}/datasets`);
  }

  getContents(bucket: string, prefix: string = ''): Observable<any> {
    return this.http.get(`${this.apiUrl}/buckets/${bucket}/browse?prefix=${prefix}`);
  }

  // --- [Training 관련] ---
  startTraining(payload: { dataset: string, epochs: number, batch: number, model_variant: string }): Observable<any> {
    return this.http.post(`${this.apiUrl}/train`, payload);
  }

  // --- [MLflow 관련: 핵심 수정 사항] ---

  // 1. 모든 실험 목록 가져오기
  getExperiments(): Observable<Experiment[]> {
    return this.http.get<Experiment[]>(`${this.apiUrl}/experiments`);
  }

  // 2. 특정 실험에 속한 실행(Run) 목록 가져오기
  getRunsByExperiment(experimentId: string): Observable<MLflowRun[]> {
    return this.http.get<MLflowRun[]>(`${this.apiUrl}/experiments/${experimentId}/runs`);
  }

  // --- [Log 관련: SSE 실시간 스트리밍] ---
  // SSE는 HttpClient가 아닌 EventSource를 사용해야 합니다.
  getLogStream(containerId: string): EventSource {
    return new EventSource(`${this.apiUrl}/train/${containerId}/logs`);
  }

  /**
   * 1. 특정 Run의 메트릭 히스토리 가져오기 (Chart.js 시각화용)
   * mAP, Loss 등의 변화 추이를 리스트 형태로 반환합니다.
   */
  getMetricsHistory(runId: string): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/runs/${runId}/metrics/history`);
  }

  /**
   * 2. MLflow에 저장된 학습 결과 이미지 URL 생성
   * HTML <img> 태그의 [src]에 직접 바인딩하기 위해 URL 문자열을 반환합니다.
   */
  getArtifactPreviewUrl(runId: string, filename: string): string {
    return `${this.apiUrl}/runs/${runId}/artifacts/preview?filename=${filename}`;
  }

  // --- [BentoML 배포 관련] ---

  /**
   * 3. BentoML 빌드 및 배포 시작
   * 서버의 백그라운드 태스크를 트리거합니다.
   */
  deployToBento(runId: string): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/runs/${runId}/deploy`, {});
  }

  /**
   * 4. BentoML 배포 상태 실시간 수신 (SSE)
   * 전역 상태 스트림을 사용하거나 별도의 배포 상태 스트림을 연결합니다.
   */
  getStatusStream(): EventSource {
    return new EventSource(`${this.apiUrl}/train/status-stream`);
  }

  /**
   * 1. 특정 상태(예: 'FINISHED')의 모든 Run 가져오기
   * 모든 실험을 훑어서 성공적으로 끝난 모델들만 필터링하여 가져옵니다.
   */
  getRunsByStatus(status: string): Observable<MLflowRun[]> {
    return this.http.get<MLflowRun[]>(`${this.apiUrl}/runs/status/${status}`);
  }

  /**
   * 2. 현재 활성화된(Serving 중인) 서비스 목록 가져오기
   */
  getActiveServices(): Observable<any[]> {
    return this.http.get<any[]>(`${this.apiUrl}/deployments/active`);
  }

  /**
   * 3. 배포된 모델에 추론 요청 (이미지 업로드)
   */
  predict(runId: string, imageFile: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', imageFile); // 서버의 UploadFile 이름과 일치해야 함
    return this.http.post<any>(`${this.apiUrl}/runs/${runId}/predict`, formData);
  }
  
}
