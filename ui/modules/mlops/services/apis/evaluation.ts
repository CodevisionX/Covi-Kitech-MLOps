import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { catchError, Observable } from 'rxjs';
import { BaseApi } from './baseApi';
import { environment } from '../../../../src/environments/environment';
import { IEvaluation, IEvaluationCreate } from './models/evaluation.model';

@Injectable({ providedIn: 'root' })
export class EvaluationApi extends BaseApi {
  private http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl;

  create(body: IEvaluationCreate): Observable<IEvaluation> {
    return this.http.post<IEvaluation>('/evaluations', body).pipe(catchError(this.handleError));
  }

  list(projectId?: number): Observable<IEvaluation[]> {
    let params = new HttpParams();
    if (projectId) params = params.set('project_id', projectId);
    return this.http.get<IEvaluation[]>('/evaluations', { params }).pipe(catchError(this.handleError));
  }

  get(id: number): Observable<IEvaluation> {
    return this.http.get<IEvaluation>(`/evaluations/${id}`).pipe(catchError(this.handleError));
  }

  getLogs(id: number): Observable<string> {
    return this.http.get(`/evaluations/${id}/logs`, { responseType: 'text' }).pipe(catchError(this.handleError));
  }

  /** 슬롯별 결과 CSV (UTF-8 BOM 포함) */
  getPredictionsCsv(id: number): Observable<string> {
    return this.http.get(`/evaluations/${id}/predictions`, { responseType: 'text' }).pipe(catchError(this.handleError));
  }

  predictionsUrl(id: number): string {
    return `${this.baseUrl}/api/v1/evaluations/${id}/predictions`;
  }

  /** 평가에 쓴 패널 이미지 + 검출 박스 (선택 슬롯 강조) */
  panelImageUrl(id: number, r: { image: string; panel: string; slot?: string; result?: string }): string {
    const q = new URLSearchParams({ image: r.image, panel: r.panel });
    if (r.slot) q.set('slot', r.slot);
    if (r.result) q.set('result', r.result);
    return `${this.baseUrl}/api/v1/evaluations/${id}/panel-image?${q}`;
  }

  /** 인식 모델에 들어간 슬롯 이미지 */
  slotCropUrl(id: number, r: { image: string; panel: string; slot: string }): string {
    const q = new URLSearchParams({ image: r.image, panel: r.panel, slot: r.slot });
    return `${this.baseUrl}/api/v1/evaluations/${id}/slot-crop?${q}`;
  }

  /** 현장 폴더 구조의 배포 패키지 zip (브라우저가 바로 내려받음) */
  packageUrl(id: number): string {
    return `${this.baseUrl}/api/v1/evaluations/${id}/package`;
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`/evaluations/${id}`).pipe(catchError(this.handleError));
  }
}
