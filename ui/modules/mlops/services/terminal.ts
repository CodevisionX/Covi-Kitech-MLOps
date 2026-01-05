import { Injectable, signal, inject, NgZone } from '@angular/core';
import { Subscription } from 'rxjs';
import { Jobs } from './apis/job';
import { Deployment } from './apis/deployment';

export type TerminalStatus = 'idle' | 'running' | 'completed' | 'error';

@Injectable({ providedIn: 'root' })
export class TerminalService {
  
  private zone = inject(NgZone);
  private readonly deploymentService = inject(Deployment);
  private readonly jobService = inject(Jobs);

  logs = signal<string[]>([]);
  status = signal<TerminalStatus>('idle');
  currentId = signal<number | null>(null);
  currentType = signal<'job' | 'deployment' | null>(null);

  private streamSubscription: Subscription | null = null;
  private logsArray: string[] = [];
  private readonly MAX_LOG_LINES = 1000;
  private lastUpdateTicket: any; // 시간 기반 업데이트를 위한 티켓

  // ANSI 코드 제거 (터미널 색상 코드 등)
  private stripAnsi(line: string): string {
    return line.replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
  }

  // 로그 하이라이팅 (YOLO 및 BentoML 대응)
  private highlightLog(line: string): string {
    if (!line) return '';
    const cleanLine = this.stripAnsi(line);
    return cleanLine
      .replace(/(Epoch \d+\/\d+)/g, '<span class="hl-epoch">$1</span>')
      .replace(/(box_loss|cls_loss|dfl_loss|precision_B|recall_B|mAP50_B)/g, '<span class="hl-metric">$1</span>')
      .replace(/(Successfully|FINISHED|SUCCESS|Training completed|Running on)/gi, '<span class="hl-success">$1</span>')
      .replace(/(Error|FAILED|Exception|Traceback|Critical)/gi, '<span class="hl-error">$1</span>');
  }

  /**
   * 스트리밍 또는 정적 로그 시작
   */
  startStreaming(id: number, status: string, type: 'job' | 'deployment') {
    this.close(); // 기존 리셋
    this.currentId.set(id);
    this.currentType.set(type);

    const isJobRunning = type === 'job' && ['RUNNING', 'PENDING'].includes(status);
    const isDeployRunning = type === 'deployment' && ['REGISTERING', 'BUILDING', 'CREATING', 'RUNNING'].includes(status);

    if (isJobRunning || isDeployRunning) {
      this.status.set('running');
      this.subscribeStream(id, type);
    } else {
      this.status.set('completed');
      if (type === 'job') {
        this.loadJobStaticLogs(id);
      } else {
        this.logs.set(['[System] 해당 서비스가 종료되어 실시간 로그를 가져올 수 없습니다.']);
      }
    }
  }

  /**
   * 실시간 SSE 스트림 구독 (Job/Deployment 분기)
   */
  private subscribeStream(id: number, type: 'job' | 'deployment') {
    const stream$ = type === 'job' 
      ? this.jobService.getJobLogStream(id) 
      : this.deploymentService.getDeploymentLogStream(id);

    this.streamSubscription = stream$.subscribe({
      next: (sseEvent) => this.processLogLine(sseEvent),
      error: (err) => {
        this.status.set('error');
        this.processLogLine({ data: `[System] 로그 연결 에러: ${err.message || 'Unknown Error'}` });
      }
    });
  }

  /**
   * 저장된 과거 학습 로그 로드 (Job 전용)
   */
  private loadJobStaticLogs(id: number) {
    this.jobService.getStaticLogs(id).subscribe({
      next: (res) => {
        if (res && res.logs) {
          const lines = res.logs.split('\n');
          this.logsArray = lines.map(line => this.highlightLog(line.trimEnd()));
          this.logs.set([...this.logsArray]);
        }
      },
      error: () => {
        this.status.set('error');
        this.logs.set(['[System] 로그 파일을 불러오는데 실패했습니다.']);
      }
    });
  }

  /**
   * 성능 최적화된 로그 라인 처리 (스로틀링 적용)
   */
  private processLogLine(sseEvent: any) {
    this.zone.runOutsideAngular(() => {
      const rawLine = (sseEvent && sseEvent.data) ? String(sseEvent.data) : String(sseEvent);
      if (!rawLine || rawLine.trim() === '') return;

      const highlighted = this.highlightLog(rawLine.trimEnd());
      this.logsArray.push(highlighted);

      if (this.logsArray.length > this.MAX_LOG_LINES) {
        this.logsArray.shift();
      }

      if (this.lastUpdateTicket) return;

      this.lastUpdateTicket = setTimeout(() => {
        this.zone.run(() => {
          this.logs.set([...this.logsArray]);
          this.lastUpdateTicket = null;
        });
      }, 200);
    });
  }

  /**
   * 리소스 정리 및 상태 리셋
   */
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
    this.currentId.set(null); // currentJobId 대신 정의된 currentId 사용
    this.status.set('idle');
  }

}