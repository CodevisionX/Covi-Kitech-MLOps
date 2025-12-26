import { Injectable, signal, inject, NgZone } from '@angular/core';
import { environment } from './../../../src/environments/environment';
import { Subscription } from 'rxjs';
import { Training } from './apis/training';

export type TerminalStatus = 'idle' | 'running' | 'completed' | 'error';

@Injectable({ providedIn: 'root' })
export class TerminalService {

  private apiUrl = environment.apiUrl;
  private zone = inject(NgZone);
  private readonly training = inject(Training);

  // 상태 관리 시그널
  logs = signal<string[]>([]);
  currentContainerId = signal<string | null>(null);
  currentRunId = signal<string | null>(null);       // 빌드용 (Run ID)
  status = signal<TerminalStatus>('running');
  isMinimized = signal(false);

  private streamSubscription: Subscription | null = null;

  private highlightLog(line: string): string {
    if (!line) return '';
    return line
      .replace(/(Epoch \d+\/\d+)/g, '<span class="hl-epoch">$1</span>')
      .replace(/(box_loss|cls_loss|dfl_loss)/g, '<span class="hl-metric">$1</span>')
      .replace(/(\d+\.\d+G)/g, '<span class="hl-gpu">$1</span>')
      .replace(/(Successfully|FINISHED|SUCCESS)/gi, '<span class="hl-success">$1</span>')
      .replace(/(Error|FAILED|Exception|Traceback)/gi, '<span class="hl-error">$1</span>');
  }

  startStreaming(containerId: string) {
    this.stopExistingStream(); // 이전 연결 확실히 종료
    this.currentContainerId.set(containerId);
    this.currentRunId.set(null);
    this.logs.set([]);
    this.status.set('running');
    this.isMinimized.set(false);

    // 직접 EventSource를 만들지 않고, Training 서비스의 메서드를 구독합니다.
    this.streamSubscription = this.training.getLogStream(containerId).subscribe({
      next: (data) => {
        this.processLogLine(data);
      },
      error: (err) => {
        console.error('Log Stream Error:', err);
        this.status.set('error');
        this.handleStreamEnd();
      },
      complete: () => {
        this.handleStreamEnd();
      }
    });
  }

  startBuildStreaming(runId: string) {
    this.stopExistingStream();
    this.currentRunId.set(runId);
    this.currentContainerId.set(null);
    this.logs.set(["BentoML 빌드 프로세스를 초기화 중입니다..."]);
    this.status.set('running');
    this.isMinimized.set(false);

    this.streamSubscription = this.training.getStatusStream().subscribe({
      next: (data) => {
        if (data.run_id === runId) {
          if (data.event === 'bento_log') {
            this.processLogLine(`[BUILD] ${data.message}`);
          }
          if (data.event === 'bento_status') {
            this.processLogLine(`[STATUS] ${data.message || data.status}`);
            if (data.status === 'SUCCESS') {
              this.status.set('completed');
              this.stopExistingStream();
            } else if (data.status === 'FAILED') {
              this.status.set('error');
              this.stopExistingStream();
            }
          }
        }
      },
      error: (err) => {
        console.error('Build Status Stream Error:', err);
        this.status.set('error');
      }
    });
  }

  private processLogLine(data: any) {
    this.zone.run(() => {
      // 💡 전달받은 데이터가 객체인 경우 'message' 필드를 추출, 아니면 그대로 사용
      const rawLine = typeof data === 'string' ? data : (data.message || '');

      // 이제 문자열이 확실하므로 .trimEnd()를 사용할 수 있습니다.
      const cleanLine = rawLine.trimEnd();
      const highlighted = this.highlightLog(cleanLine);

      this.logs.update(prev => {
        if (prev.length === 0) return [highlighted];

        const newLogs = [...prev];
        const lastLine = newLogs[newLogs.length - 1];

        const currentPrefix = cleanLine.substring(0, 20);

        if (cleanLine.includes('\r') || (cleanLine.includes('%') && lastLine.includes(currentPrefix))) {
          newLogs[newLogs.length - 1] = highlighted.replace(/\r/g, '');
          return newLogs;
        }

        return [...newLogs, highlighted];
      });
    });
  }

  private handleStreamEnd() {
    const lastFewLogs = this.logs().slice(-5).join('\n');
    const hasError = /error|fail|exception|traceback/i.test(lastFewLogs);
    this.status.set(hasError ? 'error' : 'completed');
  }

  // 연결만 끊는 함수
  stopExistingStream() {
    if (this.streamSubscription) {
      this.streamSubscription.unsubscribe();
      this.streamSubscription = null;
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