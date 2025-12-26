import { Injectable, signal, inject, NgZone } from '@angular/core';
import { environment } from './../../../src/environments/environment';

export type TerminalStatus = 'idle' | 'running' | 'completed' | 'error';

@Injectable({ providedIn: 'root' })
export class TerminalService {

  private apiUrl = environment.apiUrl;
  private zone = inject(NgZone);

  // 상태 관리 시그널
  logs = signal<string[]>([]);
  currentContainerId = signal<string | null>(null);
  currentRunId = signal<string | null>(null);       // 빌드용 (Run ID)
  status = signal<TerminalStatus>('running');
  isMinimized = signal(false);
  private eventSource: EventSource | null = null;

  private highlightLog(line: string): string {
    if (!line) return '';

    // 1. 숫자 및 핵심 지표 하이라이트 (Regex 사용)
    let highlighted = line
      .replace(/(Epoch \d+\/\d+)/g, '<span class="hl-epoch">$1</span>')
      .replace(/(box_loss|cls_loss|dfl_loss)/g, '<span class="hl-metric">$1</span>')
      .replace(/(\d+\.\d+G)/g, '<span class="hl-gpu">$1</span>')
      .replace(/(Successfully|FINISHED|SUCCESS)/gi, '<span class="hl-success">$1</span>')
      .replace(/(Error|FAILED|Exception|Traceback)/gi, '<span class="hl-error">$1</span>');

    return highlighted;
  }

  startStreaming(containerId: string) {
    this.stopExistingStream();
    this.currentContainerId.set(containerId);
    this.currentRunId.set(null);
    this.logs.set([]);
    this.status.set('running');
    this.isMinimized.set(false);

    // 서버의 로그 엔드포인트 연결
    this.eventSource = new EventSource(`${this.apiUrl}/train/${containerId}/logs`);

    // terminal.service.ts
    this.eventSource.onmessage = (event) => {
      this.zone.run(() => {
        if (!event.data) return;

        const logLine = event.data.trimEnd(); // 끝의 불필요한 공백 제거

        this.logs.update(prev => {
          if (prev.length === 0) return [logLine];

          const newLogs = [...prev];
          const lastLine = newLogs[newLogs.length - 1];

          // 1. 진행 바 패턴 인식 (Epoch 번호나 'Class' 헤더 등이 같은지 확인)
          // 예: "77/100" 으로 시작하는 로그가 연속으로 들어오면 덮어쓰기
          const currentPrefix = logLine.substring(0, 20); // 앞의 20자 정도를 비교 키로 사용
          const lastPrefix = lastLine.substring(0, 20);

          // 2. 만약 현재 줄에 \r이 있거나, 앞부분이 이전 줄과 매우 유사하다면 (진행률 업데이트 상황)
          if (logLine.includes('\r') || (currentPrefix === lastPrefix && logLine.includes('%'))) {
            newLogs[newLogs.length - 1] = logLine.replace(/\r/g, ''); // 마지막 줄 교체
            return newLogs;
          }

          // 3. 완전히 새로운 로그라면 추가
          return [...newLogs, logLine];
        });
      });
    };

    this.eventSource.onerror = () => {
      this.zone.run(() => this.handleStreamEnd(containerId));
    };
  }

  startBuildStreaming(runId: string) {
    this.stopExistingStream();
    this.currentRunId.set(runId);
    this.currentContainerId.set(null);
    this.logs.set(["BentoML 빌드 프로세스를 초기화 중입니다..."]);
    this.status.set('running');
    this.isMinimized.set(false);

    // 공통 상태 스트림 구독
    this.eventSource = new EventSource(`${this.apiUrl}/train/status-stream`);

    this.eventSource.onmessage = (event) => {
      this.zone.run(() => {
        const data = JSON.parse(event.data);

        // 내 Run ID와 관련된 데이터만 필터링
        if (data.run_id === runId) {
          // 빌드 로그 메시지 처리
          if (data.event === 'bento_log') {
            this.logs.update(prev => [...prev, `[BUILD] ${data.message}`]);
          }

          // 빌드 상태 변경 처리 (SUCCESS / FAILED)
          if (data.event === 'bento_status') {
            this.logs.update(prev => [...prev, `[STATUS] ${data.message || data.status}`]);

            if (data.status === 'SUCCESS') {
              this.status.set('completed');
              this.stopExistingStream(); // 성공 시 스트림 종료
            } else if (data.status === 'FAILED') {
              this.status.set('error');
              this.stopExistingStream(); // 실패 시 스트림 종료
            }
          }
        }
      });
    };

    this.eventSource.onerror = (err) => {
      console.error('Build Status Stream Error:', err);
      // 에러 발생 시 재연결 로직은 브라우저 기본 EventSource가 자동으로 수행함
    };
  }

  private handleStreamEnd(id: string) {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    const lastFewLogs = this.logs().slice(-5).join('\n');
    const hasError = /error|fail|exception|traceback/i.test(lastFewLogs);
    this.status.set(hasError ? 'error' : 'completed');

    console.log(`Stream closed for ${id}. Final status: ${this.status()}`);
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
    this.currentRunId.set(null);
    this.logs.set([]);
    this.status.set('idle');
  }

}