import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Sse } from './sse';
import { BaseApi } from './baseApi';
import { Observable, catchError } from 'rxjs';
import { environment } from './../../../../src/environments/environment';
import { IJobResponse, ITrainingJob, ITrainRequest } from './models/training.model';

@Injectable({
  providedIn: 'root',
})
export class Training extends BaseApi {
  
  private http = inject(HttpClient);
  private sse = inject(Sse);
  
  start(payload: ITrainRequest): Observable<IJobResponse> {
    return this.http.post<IJobResponse>('/training', payload).pipe(
      catchError(this.handleError)
    );
  }

  getLogStream(containerId: string): Observable<any> {
    const url = `${environment.apiUrl}/api/v1/training/${containerId}/logs`;
    return this.sse.getServerSentEvent(url);
  }

  getActiveJobs(): Observable<ITrainingJob[]> {
    return this.http.get<ITrainingJob[]>('/training/active');
  }

  getHistory(): Observable<ITrainingJob[]> {
    return this.http.get<ITrainingJob[]>('/training/history');
  }

  cancel(jobId: number): Observable<any> {
    return this.http.post(`/training/${jobId}/cancel`, {});
  }

  getStatusStream(): Observable<any> {
    const url = `${environment.apiUrl}/api/v1/training/status-stream`;
    return this.sse.getServerSentEvent(url);
  }
  
}
