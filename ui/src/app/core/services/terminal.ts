import { Injectable, signal, inject, NgZone } from '@angular/core';
import { environment } from '../../../environments/environment';

export type TerminalStatus = 'running' | 'completed' | 'error';

@Injectable({ providedIn: 'root' })
export class TerminalService {

  private apiUrl = environment.apiUrl;
  private zone = inject(NgZone);
  
  // 상태 관리 시그널
  logs = signal<string[]>([]);
  currentContainerId = signal<string | null>(null);
  status = signal<TerminalStatus>('running');
  isMinimized = signal(false);
  private eventSource: EventSource | null = null;

  startStreaming(containerId: string) {
    this.stopExistingStream(); // 기존 연결만 정리 (로그는 아래서 초기화)
    this.currentContainerId.set(containerId);
    this.logs.set([]);
    this.status.set('running'); // ✅ 시작 시 'running'
    this.isMinimized.set(false);

    this.eventSource = new EventSource(`${this.apiUrl}/train/${containerId}/logs`);

    this.eventSource.onmessage = (event) => {
      this.zone.run(() => {
        if (event.data) {
          this.logs.update(prev => [...prev, event.data]);
        }
      });
    };

    this.eventSource.onerror = () => {
      this.zone.run(() => {
        // ✅ 핵심: 연결만 끊고 UI(Id, logs)는 그대로 둡니다.
        if (this.eventSource) {
          this.eventSource.close();
          this.eventSource = null;
        }
        
        // 마지막 로그에 따라 성공/실패 상태 업데이트
        const lastLog = this.logs()[this.logs().length - 1] || '';
        if (lastLog.includes('ERROR') || lastLog.includes('RuntimeError')) {
          this.status.set('error');
        } else {
          this.status.set('completed'); // ✅ 전송 종료 시 '완료'로 변경
        }
      });
    };
  }

  // 연결만 끊는 함수
  private stopExistingStream() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  minimize() { this.isMinimized.set(true); }
  restore() { this.isMinimized.set(false); }

  close() {
    this.stopExistingStream();
    this.currentContainerId.set(null);
    this.logs.set([]);
  }
  
}