import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { BaseApi } from './baseApi';

@Injectable({
  providedIn: 'root',
})
export class Deployment extends BaseApi {

  private http = inject(HttpClient);

  deploy(runId: string): Observable<any> {
    return this.http.post(`/runs/${runId}/deploy`, {});
  }

  getActiveServices(): Observable<any[]> {
    return this.http.get<any[]>('/deployments/active');
  }

  predict(runId: string, imageFile: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', imageFile);
    return this.http.post<any>(`/runs/${runId}/predict`, formData);
  }
  
}