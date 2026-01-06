import { inject, Injectable, NgZone } from '@angular/core';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root',
})
export class Sse {

  private zone = inject(NgZone);

  /**
   * SSE 연결을 생성하고 Observable로 반환합니다.
   */
  getServerSentEvent(url: string, eventTypes: string[] = []): Observable<any> {
    return new Observable(observer => {
      const eventSource = new EventSource(url);

      // 1. 이름이 없는 기본 이벤트 (data: ...만 있는 경우) 처리
      eventSource.onmessage = event => {
        this.zone.run(() => {
          observer.next({ event: 'message', data: this.parse(event.data) });
        });
      };

      // 2. 백엔드에서 지정한 네임드 이벤트(job_status 등) 처리
      eventTypes.forEach(type => {
        eventSource.addEventListener(type, (event: MessageEvent) => {
          this.zone.run(() => {
            observer.next({ event: type, data: this.parse(event.data) });
          });
        });
      });

      eventSource.onerror = error => {
        if (eventSource.readyState === 2) {
          this.zone.run(() => observer.error(error));
        }
      };

      return () => {
        console.log('물리적 SSE 연결 종료');
        eventSource.close();
      };
    });
  }

  private parse(data: any) {
    try {
      return JSON.parse(data);
    } catch {
      return data;
    }
  }

}
