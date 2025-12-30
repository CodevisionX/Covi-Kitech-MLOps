import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Sse } from './sse';
import { BaseApi } from './baseApi';
import { environment } from '../../../../src/environments/environment';
import { Observable, catchError } from 'rxjs';
import { IJobCreate } from './models/job.model';
import { IJob } from './models/job.model'

@Injectable({
  providedIn: 'root',
})
export class Jobs extends BaseApi {

  private http = inject(HttpClient);
  private sse = inject(Sse);

  private readonly baseUrl = environment.apiUrl;

  createJob(jobData: IJobCreate): Observable<IJob> {
    return this.http.post<IJob>('/jobs', jobData)
      .pipe(catchError(this.handleError));
  }

  getActiveJobs(projectId?: number): Observable<IJob[]> {
    let params = new HttpParams();
    if (projectId) {
      params = params.set('project_id', projectId.toString());
    }

    return this.http.get<IJob[]>('/jobs/active', { params })
      .pipe(catchError(this.handleError));
  }

  getJobHistory(skip: number = 0, limit: number = 20, projectId?: number): Observable<IJob[]> {
    let params = new HttpParams()
      .set('skip', skip)
      .set('limit', limit);

    if (projectId) {
      params = params.set('project_id', projectId.toString());
    }

    return this.http.get<IJob[]>('/jobs/history', { params })
      .pipe(catchError(this.handleError));
  }

  cancelJob(jobId: number): Observable<IJob> {
    return this.http.post<IJob>(`/jobs/${jobId}/cancel`, {})
      .pipe(catchError(this.handleError));
  }

  getJobUpdates(): Observable<any> {
    const url = `${this.baseUrl}/api/v1/jobs/stream`;
    // 백엔드에서 broadcast할 때 사용하는 이벤트 이름들을 배열로 전달합니다.
    return this.sse.getServerSentEvent(url, ['status_change', 'new_job']);
  }

  getJobLogStream(jobId: number): Observable<any> {
    const url = `${this.baseUrl}/api/v1/jobs/${jobId}/logs`;
    // 로그 스트림은 별도의 event 명시가 없으므로 빈 배열을 보냅니다.
    return this.sse.getServerSentEvent(url, []);
  }

  getStaticLogs(jobId: number): Observable<{ logs: string }> {
    return this.http.get<{ logs: string }>(`/jobs/${jobId}/logs/static`)
      .pipe(catchError(this.handleError));
  }

}
