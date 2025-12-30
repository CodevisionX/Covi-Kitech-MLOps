import { Injectable, signal, inject, NgZone } from '@angular/core';
import { Subscription } from 'rxjs';
import { Jobs } from './apis/job';

export type TerminalStatus = 'idle' | 'running' | 'completed' | 'error';

@Injectable({ providedIn: 'root' })
export class TerminalService {
  private zone = inject(NgZone);
  private readonly jobService = inject(Jobs);

  logs = signal<string[]>([]); // 시그널 이름 확인
  currentJobId = signal<number | null>(null);
  status = signal<TerminalStatus>('idle');

  private streamSubscription: Subscription | null = null;
  private logsArray: string[] = [];
  private readonly MAX_LOG_LINES = 1000;
  private lastUpdateTicket: any; // 시간 기반 업데이트를 위한 티켓

  private stripAnsi(line: string): string {
    return line.replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
  }

  private highlightLog(line: string): string {
    if (!line) return '';
    const cleanLine = this.stripAnsi(line);
    return cleanLine
      .replace(/(Epoch \d+\/\d+)/g, '<span class="hl-epoch">$1</span>')
      .replace(/(box_loss|cls_loss|dfl_loss|precision_B|recall_B|mAP50_B)/g, '<span class="hl-metric">$1</span>')
      .replace(/(Successfully|FINISHED|SUCCESS|Training completed)/gi, '<span class="hl-success">$1</span>')
      .replace(/(Error|FAILED|Exception|Traceback)/gi, '<span class="hl-error">$1</span>');
  }

  startStreaming(jobId: number, status: string) {
    this.close(); // 기존 리셋
    this.currentJobId.set(jobId);

    // 1. 학습 중인 상태(RUNNING, PENDING)일 때만 SSE 스트리밍
    if (status === 'RUNNING' || status === 'PENDING') {
      this.status.set('running');
      this.streamSubscription = this.jobService.getJobLogStream(jobId).subscribe({
        next: (sseEvent) => this.processLogLine(sseEvent),
        error: (err) => {
          this.status.set('error');
          this.processLogLine({ data: `[System] 연결 에러: ${err.message}` });
        }
      });
    }
    // 2. 이미 종료된 상태(FINISHED, FAILED 등)는 정적 로그 요청
    else {
      this.status.set('completed');
      // 이전에 만든 getStaticLogs API를 호출
      this.jobService.getStaticLogs(jobId).subscribe({
        next: (res) => {
          if (res && res.logs) {
            // 전체 텍스트를 줄 단위로 쪼개서 하이라이트 적용 후 저장
            const lines = res.logs.split('\n');
            this.logsArray = lines.map(line => this.highlightLog(line));
            this.logs.set([...this.logsArray]);
          }
        },
        error: (err) => {
          this.status.set('error');
          this.logs.set(['[System] 로그를 불러오는데 실패했습니다.']);
        }
      });
    }
  }

  private processLogLine(sseEvent: any) {
    this.zone.runOutsideAngular(() => {
      const rawLine = (sseEvent && sseEvent.data) ? String(sseEvent.data) : String(sseEvent);
      if (!rawLine || rawLine.trim() === '') return;

      const highlighted = this.highlightLog(rawLine.trimEnd());
      this.logsArray.push(highlighted);

      if (this.logsArray.length > this.MAX_LOG_LINES) {
        this.logsArray.shift();
      }

      // 이미 업데이트 예약이 되어 있다면 무시 (디바운싱/스로틀링)
      if (this.lastUpdateTicket) return;

      // 200ms마다 한 번씩만 시그널 업데이트 요청
      this.lastUpdateTicket = setTimeout(() => {
        this.zone.run(() => {
          this.logs.set([...this.logsArray]);
          this.lastUpdateTicket = null;
        });
      }, 200);
    });
  }

  close() {
    if (this.streamSubscription) {
      this.streamSubscription.unsubscribe();
      this.streamSubscription = null;
    }
    if (this.lastUpdateTicket) {
      clearTimeout(this.lastUpdateTicket);
      this.lastUpdateTicket = null;
    }
    this.logsArray = [];
    this.logs.set([]);
    this.currentJobId.set(null);
    this.status.set('idle');
  }
}