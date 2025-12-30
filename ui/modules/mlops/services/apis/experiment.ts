import { inject, Injectable } from '@angular/core';
import { BaseApi } from './baseApi';
import { HttpClient } from '@angular/common/http';
import { catchError, Observable } from 'rxjs';
import { environment } from './../../../../src/environments/environment';
import { IMLflowRun } from './models/experiment.model';

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
