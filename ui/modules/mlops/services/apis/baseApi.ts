import { HttpErrorResponse } from '@angular/common/http';
import { throwError } from 'rxjs';

export abstract class BaseApi {
  /**
   * 전역 에러 핸들링 로직
   * 서버에서 내려오는 다양한 에러를 공통 포맷으로 가공합니다.
   */
  protected handleError(error: HttpErrorResponse) {
    let errorMessage = '알 수 없는 오류가 발생했습니다.';
    
    if (error.error instanceof ErrorEvent) {
      // 클라이언트 측 에러
      errorMessage = `에러: ${error.error.message}`;
    } else {
      // 서버 측 에러 (FastAPI HTTPException 등)
      errorMessage = error.error?.detail || `코드: ${error.status}\n메시지: ${error.message}`;
    }
    
    console.error(errorMessage);
    return throwError(() => new Error(errorMessage));
  }
}