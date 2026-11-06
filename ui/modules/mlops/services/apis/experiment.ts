import { inject, Injectable } from '@angular/core';
import { BaseApi } from './baseApi';
import { HttpClient } from '@angular/common/http';
import { catchError, Observable } from 'rxjs';
import { environment } from '../../../../src/environments/environment';
import { IMLflowRun } from './models/experiment.model';

export interface IMetricSeries {
  status: string;
  params: Record<string, string>;
  series: Record<string, [number, number][]>;
}

@Injectable({
  providedIn: 'root',
})
export class Experiment extends BaseApi {

  private http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl;

  getExperimentsByProject(projectId: number): Observable<any[]> {
    return this.http.get<any[]>(`/projects/${projectId}/experiments`)
      .pipe(catchError(this.handleError));
  }

  /** MLflow 화면 주소. 대시보드에 접속한 주소의 호스트를 그대로 써서 다른 PC 에서 접속해도 열리게 함 */
  get mlflowUiUrl(): string {
    return `${location.protocol}//${location.hostname}:15000`;
  }

  /** 지표별 [step, 값] 목록 (학습 추이 차트용) */
  getMetricsSeries(runId: string): Observable<IMetricSeries> {
    return this.http.get<IMetricSeries>(`/experiments/${runId}/metrics/series`)
      .pipe(catchError(this.handleError));
  }

  getMetricsHistory(runId: string): Observable<any> {
    return this.http.get(`/experiments/${runId}/metrics/history`)
      .pipe(catchError(this.handleError));
  }

  getArtifactPreviewUrl(runId: string, filename: string): string {
    return `${this.baseUrl}/api/v1/experiments/${runId}/artifacts/preview?filename=${filename}`;
  }

  getRunDetail(runId: string): Observable<IMLflowRun> {
    return this.http.get<IMLflowRun>(`/experiments/runs/${runId}`)
      .pipe(catchError(this.handleError));
  }
  
}
