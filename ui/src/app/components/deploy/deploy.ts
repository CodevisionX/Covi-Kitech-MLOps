import { Component, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { Api, MLflowRun } from '../../core/services/api';
import { Notification } from '../../core/services/notification';
import { MatDialog } from '@angular/material/dialog';
import { TerminalLog } from '../dialogs/terminal-log/terminal-log';

@Component({
  selector: 'app-deploy',
  standalone: false,
  templateUrl: './deploy.html',
  styleUrl: './deploy.scss',
})
export class Deploy implements OnInit, OnDestroy {

  private dialog = inject(MatDialog);
  private readonly apiService = inject(Api);
  private readonly notificationService = inject(Notification);

  private statusEventSource?: EventSource;

  finishedRuns = signal<MLflowRun[]>([]);
  activeServices = signal<any[]>([]);
  buildStatusMap = new Map<string, string>();

  ngOnInit() {
    this.refreshData();
    this.subscribeToBuildUpdates();
  }

  ngOnDestroy(): void {
    if (this.statusEventSource) {
      this.statusEventSource.close();
      console.log('📡 [Deploy] Status-stream 연결이 성공적으로 종료되었습니다.');
    }
  }

  subscribeToBuildUpdates() {
    // API 서비스에서 생성된 EventSource를 변수에 할당
    this.statusEventSource = this.apiService.getStatusStream();

    this.statusEventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.event === 'bento_status') {
        // UI 업데이트
        this.buildStatusMap.set(data.run_id, data.status);

        // 빌드 성공 시 목록 새로고침
        if (data.status === 'SUCCESS') {
          this.refreshData();
        }
      }
    };

    this.statusEventSource.onerror = (err) => {
      console.error('SSE 연결 오류:', err);
      this.statusEventSource?.close();
    };
  }

  getBuildStatus(runId: string): string {
    return this.buildStatusMap.get(runId) || 'IDLE';
  }

  openBuildLog(runId: string) {
    this.dialog.open(TerminalLog, {
      data: { runId: runId, type: 'build' },
      width: '850px',
      height: '600px',
      panelClass: 'custom-terminal-dialog'
    });
  }

  refreshData() {
    // 1. MLflow에서 성공한 Run 목록 로드
    this.apiService.getRunsByStatus('FINISHED').subscribe({
      next: (runs) => this.finishedRuns.set(runs),
      error: () => this.notificationService.showError('학습 이력을 불러오지 못했습니다.')
    });

    // 2. 현재 실행 중인 도커/BentoML 서비스 로드
    this.apiService.getActiveServices().subscribe({
      next: (services) => this.activeServices.set(services)
    });
  }

  startBuild(runId: string) {
    this.apiService.deployToBento(runId).subscribe({
      next: () => {
        this.notificationService.showInfo('BentoML 빌드가 시작되었습니다.');
        // 빌드 상태는 SSE를 통해 업데이트되거나 수동 새로고침으로 확인
      },
      error: (err) => this.notificationService.showError('빌드 요청 실패: ' + err.message)
    });
  }

}
