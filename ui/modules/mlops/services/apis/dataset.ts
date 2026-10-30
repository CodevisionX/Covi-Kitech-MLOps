import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { catchError, Observable } from 'rxjs';
import { BaseApi } from './baseApi';
import {
  IDatasetUploadCreate, IDatasetVersion, IPresignResponse, IUploadSession,
} from './models/dataset.model';

@Injectable({ providedIn: 'root' })
export class DatasetApi extends BaseApi {
  private http = inject(HttpClient);

  createUpload(body: IDatasetUploadCreate): Observable<IUploadSession> {
    return this.http.post<IUploadSession>('/datasets/uploads', body).pipe(catchError(this.handleError));
  }

  getUpload(id: number): Observable<IUploadSession> {
    return this.http.get<IUploadSession>(`/datasets/uploads/${id}`).pipe(catchError(this.handleError));
  }

  /** 파일별 업로드 URL (한 번에 최대 1000개) */
  presign(id: number, files: { path: string; size: number }[]): Observable<IPresignResponse> {
    return this.http.post<IPresignResponse>(`/datasets/uploads/${id}/presign`, { files })
      .pipe(catchError(this.handleError));
  }

  completeMultipart(id: number, path: string, uploadId: string,
    parts: { part_number: number; etag: string }[]): Observable<void> {
    return this.http.post<void>(`/datasets/uploads/${id}/multipart/complete`,
      { path, upload_id: uploadId, parts }).pipe(catchError(this.handleError));
  }

  abortMultipart(id: number, path: string, uploadId: string): Observable<void> {
    return this.http.post<void>(`/datasets/uploads/${id}/multipart/abort`, { path, upload_id: uploadId })
      .pipe(catchError(this.handleError));
  }

  stagingSummary(id: number): Observable<{ file_count: number; total_bytes: number }> {
    return this.http.get<{ file_count: number; total_bytes: number }>(`/datasets/uploads/${id}/summary`)
      .pipe(catchError(this.handleError));
  }

  validate(id: number): Observable<IDatasetVersion> {
    return this.http.post<IDatasetVersion>(`/datasets/uploads/${id}/validate`, {})
      .pipe(catchError(this.handleError));
  }

  listVersions(filter: { project_id?: number; name?: string; task?: string; status?: string } = {}):
    Observable<IDatasetVersion[]> {
    let params = new HttpParams();
    Object.entries(filter).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') params = params.set(k, String(v)); });
    return this.http.get<IDatasetVersion[]>('/datasets/versions', { params }).pipe(catchError(this.handleError));
  }

  getVersion(id: number): Observable<IDatasetVersion> {
    return this.http.get<IDatasetVersion>(`/datasets/versions/${id}`).pipe(catchError(this.handleError));
  }

  getLogs(id: number): Observable<string> {
    return this.http.get(`/datasets/versions/${id}/logs`, { responseType: 'text' }).pipe(catchError(this.handleError));
  }

  deleteVersion(id: number): Observable<void> {
    return this.http.delete<void>(`/datasets/versions/${id}`).pipe(catchError(this.handleError));
  }
}
