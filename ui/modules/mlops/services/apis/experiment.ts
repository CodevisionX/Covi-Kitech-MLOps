import { inject, Injectable } from '@angular/core';
import { BaseApi } from './baseApi';
import { HttpClient } from '@angular/common/http';
import { catchError, Observable } from 'rxjs';
import { environment } from './../../../../src/environments/environment';
import { IExperiment, IMLflowRun } from './models/experiment.model';

@Injectable({
  providedIn: 'root',
})
export class Experiment extends BaseApi {

  private http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl;

  getAll(): Observable<IExperiment[]> {
    return this.http.get<IExperiment[]>('/experiments');
  }

  getRunsByExperiment(experimentId: string): Observable<IMLflowRun[]> {
    return this.http.get<IMLflowRun[]>(`/experiments/${experimentId}/runs`)
      .pipe(catchError(this.handleError));
  }

  getRunsByStatus(status: string): Observable<IMLflowRun[]> {
    return this.http.get<IMLflowRun[]>(`/experiments/status/${status}`)
      .pipe(catchError(this.handleError));
  }

  getMetricsHistory(runId: string): Observable<any> {
    return this.http.get(`/experiments/${runId}/metrics/history`);
  }

  getArtifactPreviewUrl(runId: string, filename: string): string {
    return `${this.baseUrl}/api/v1/experiments/${runId}/artifacts/preview?filename=${filename}`;
  }
  
}
