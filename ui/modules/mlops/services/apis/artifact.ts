import { inject, Injectable } from '@angular/core';
import { BaseApi } from './baseApi';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError } from 'rxjs';

@Injectable({
  providedIn: 'root',
})
export class Artifact extends BaseApi {

  private http = inject(HttpClient);

  getBuckets(): Observable<{ datasets: string[] }> {
    return this.http.get<{ datasets: string[] }>('/artifacts/datasets')
      .pipe(catchError(this.handleError));
  }

  getContents(bucket: string, prefix: string = ''): Observable<any> {
    return this.http.get(`/artifacts/browse/${bucket}`, { params: { prefix } })
      .pipe(catchError(this.handleError));
  }
  
}
