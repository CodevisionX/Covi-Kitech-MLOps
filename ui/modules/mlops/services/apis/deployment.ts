import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { catchError, Observable } from 'rxjs';
import { BaseApi } from './baseApi';
import { Sse } from './sse';
import { environment } from '../../../../src/environments/environment';
import { IDeployment, IDeploymentCreate } from './models/deployment.model';

@Injectable({
  providedIn: 'root',
})
export class Deployment extends BaseApi {

  private http = inject(HttpClient);
  private sseService = inject(Sse);
  private readonly baseUrl = environment.apiUrl;

  /**
   * 새로운 모델 배포 요청을 생성합니다.
   */
  createDeployment(deploymentData: IDeploymentCreate): Observable<IDeployment> {
    return this.http.post<IDeployment>('/deployments/', deploymentData)
      .pipe(catchError(this.handleError));
  }

  /**
   * 현재 활성화된(준비 중이거나 실행 중인) 배포 목록을 가져옵니다.
   */
  getActiveDeployments(projectId?: number): Observable<IDeployment[]> {
    let params = new HttpParams();
    if (projectId) {
      params = params.set('project_id', projectId.toString());
    }

    return this.http.get<IDeployment[]>('/deployments/active', { params })
      .pipe(catchError(this.handleError));
  }

  /**
   * 특정 배포 상세 정보를 가져옵니다.
   */
  getDeploymentById(deploymentId: number): Observable<IDeployment> {
    return this.http.get<IDeployment>(`/deployments/${deploymentId}`)
      .pipe(catchError(this.handleError));
  }

  /**
   * 실행 중인 배포 서비스를 중단하고 리소스를 반납합니다.
   */
  stopDeployment(deploymentId: number): Observable<IDeployment> {
    return this.http.post<IDeployment>(`/deployments/${deploymentId}/stop`, {})
      .pipe(catchError(this.handleError));
  }

  /**
   * SSE를 통해 배포 상태 업데이트를 실시간으로 구독합니다.
   * 백엔드에서 broadcast하는 'deployment_status' 이벤트를 수신합니다.
   */
  getDeploymentUpdates(): Observable<any> {
    const url = `${this.baseUrl}/api/v1/jobs/stream`; // 통합 SSE 엔드포인트 활용
    return this.sseService.getServerSentEvent(url, ['deployment_status']);
  }

  /**
   * 특정 배포 컨테이너(BentoML)의 로그를 실시간으로 스트리밍합니다.
   */
  getDeploymentLogStream(deploymentId: number): Observable<any> {
    const url = `${this.baseUrl}/api/v1/deployments/${deploymentId}/logs`;
    return this.sseService.getServerSentEvent(url, []);
  }

  /**
   * 배포된 모델에 이미지를 전송하여 시각화된(Bounding Box) 결과 이미지를 받습니다.
   * 반환 타입은 Blob(이미지 바이너리)입니다.
   */
  predictVisual(deploymentId: number, file: File): Observable<Blob> {
    const formData = new FormData();
    formData.append('upload_file', file); 

    return this.http.post(`/deployments/${deploymentId}/predict_visual`, formData, {
      responseType: 'blob'
    }).pipe(catchError(this.handleError));
  }
  
}