import { Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root',
})
export class Api {
  
  private apiUrl = environment.apiUrl;
  
  constructor(private http: HttpClient) {}

  // MinIO 관련
  getBuckets(): Observable<{ datasets: string[] }> {
    return this.http.get<{ datasets: string[] }>(`${this.apiUrl}/datasets`);
  }

  // 2. 특정 경로의 폴더/파일 목록 가져오기
  getContents(bucket: string, prefix: string = ''): Observable<any> {
    return this.http.get(`${this.apiUrl}/buckets/${bucket}/browse?prefix=${prefix}`);
  }

  uploadDataset(formData: FormData): Observable<any> {
    return this.http.post(`${this.apiUrl}/upload`, formData);
  }

  // Training 관련
  startTraining(config: any): Observable<any> {
    return this.http.post(`${this.apiUrl}/train`, config);
  }

  // Model List 관련 (MLflow 연동)
  getModels(): Observable<any[]> {
    return this.http.get<any[]>(`${this.apiUrl}/models`);
  }
  
}
