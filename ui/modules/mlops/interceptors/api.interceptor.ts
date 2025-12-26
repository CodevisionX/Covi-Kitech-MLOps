import { HttpInterceptorFn } from '@angular/common/http';
import { environment} from './../../../src/environments/environment';

export const apiInterceptor: HttpInterceptorFn = (req, next) => {
  // 절대 경로(http)이거나 에셋 파일 요청이 아닌 경우에만 접두사 추가
  if (!req.url.startsWith('http') && !req.url.startsWith('./assets')) {
    const apiReq = req.clone({
      url: `${environment.apiUrl}/api/v1${req.url.startsWith('/') ? '' : '/'}${req.url}`
    });
    return next(apiReq);
  }
  return next(req);
};