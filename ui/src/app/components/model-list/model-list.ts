import { Component, computed, effect, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { Api, Experiment, MLflowRun } from '../../core/services/api';
import { MatDialog } from '@angular/material/dialog';
import { TerminalLog } from '../dialogs/terminal-log/terminal-log';
import { Notification } from '../../core/services/notification';
import { ActivatedRoute, Router } from '@angular/router';
import { environment } from '../../../environments/environment';

// 페이지를 떠날 때 SSE 연결을 끊어주는 것
// 그렇지 않으면 백엔드의 sse_manager.subscribers가 계속 쌓이게 됨

@Component({
  selector: 'app-model-list',
  standalone: false,
  templateUrl: './model-list.html',
  styleUrl: './model-list.scss',
})
export class ModelList implements OnInit, OnDestroy {

  private readonly router = inject(Router);
  private apiService = inject(Api);
  private dialog = inject(MatDialog);
  private readonly route = inject(ActivatedRoute);
  private notificationService = inject(Notification);

  private eventSource?: EventSource;
  private apiUrl = environment.apiUrl;

  activeDisplayedColumns: string[] = ['modelInfo', 'status', 'startTime', 'dashboard', 'actions'];
  historyDisplayedColumns: string[] = ['modelInfo', 'status', 'startTime', 'dashboard', 'management', 'actions'];

  // 1. 상태 관리 Signal
  experiments = signal<Experiment[]>([]);
  selectedExpId = signal<string>(''); // 선택된 실험 ID
  trainingJobs = signal<MLflowRun[]>([]); // 현재 표시중인 실행 목록
  isLoading = signal<boolean>(false);

  // 2. 상태별 필터링 (Computed)
  activeJobs = computed(() => {
    return this.trainingJobs().filter(job =>
      job.status === 'RUNNING' || job.status === 'SCHEDULED'
    );
  });

  historyJobs = computed(() => {
    return this.trainingJobs().filter(job =>
      job.status !== 'RUNNING' && job.status !== 'SCHEDULED'
    );
  });

  constructor() {
    // 3. 선택된 실험이 바뀔 때마다 자동으로 실행 목록을 다시 불러옴
    effect(() => {
      const id = this.selectedExpId();
      if (id) {
        this.loadRuns(id);
      }
    }, { allowSignalWrites: true });
  }

  ngOnInit() {
    this.loadInitialData();
    this.subscribeToUpdates();
  }

  ngOnDestroy() {
    if (this.eventSource) {
      this.eventSource.close();
      console.log('📡 SSE (status-stream) 연결이 안전하게 종료되었습니다.');
    }
  }

  // 데이터 로드: 실험 목록 가져오기
  loadInitialData() {
    this.isLoading.set(true);

    this.apiService.getExperiments().subscribe({
      next: (exps) => {
        this.experiments.set(exps);

        const queryExpId = this.route.snapshot.queryParamMap.get('expId');
        const targetAlgo = this.route.snapshot.queryParamMap.get('algorithm');

        if (queryExpId && exps.some(e => e.experiment_id === queryExpId)) {
          this.selectedExpId.set(queryExpId);
        }
        else if (targetAlgo) {
          const found = exps.find(e => e.name.includes(targetAlgo));
          if (found) {
            this.selectedExpId.set(found.experiment_id);
          } else if (exps.length > 0) {
            this.selectedExpId.set(exps[0].experiment_id);
          }
        }
        else if (exps.length > 0) {
          this.selectedExpId.set(exps[0].experiment_id);
        } else {
          this.isLoading.set(false);
        }
      },
      error: (err) => {
        this.notificationService.showError('실험 목록 로드 실패');
        this.isLoading.set(false);
      }
    });
  }

  // 특정 실험의 실행 목록 로드
  loadRuns(expId: string) {
    this.isLoading.set(true);
    this.apiService.getRunsByExperiment(expId).subscribe({
      next: (runs) => {
        this.trainingJobs.set(runs);
        this.isLoading.set(false);
      },
      error: (err) => {
        this.isLoading.set(false);
        this.notificationService.showError('내역 로드 실패');
      }
    });
  }

  // 탭 변경 시 호출
  onAlgorithmChange(expId: string) {
    this.selectedExpId.set(expId);

    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { expId: expId },
      queryParamsHandling: 'merge', // 기존의 다른 쿼리 파라미터(알고리즘 등)가 있다면 유지
    });
  }

  // 시간 변환 유틸리티
  getRelativeTime(timestamp: number) {
    if (!timestamp) return '-';
    const now = Date.now();
    const diff = Math.floor((now - timestamp) / 1000);
    if (diff < 60) return '방금 전';
    if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
    return new Date(timestamp).toLocaleString();
  }

  openLogDialog(containerId: string) {
    if (!containerId) {
      this.notificationService.showWarning('컨테이너 ID가 없는 작업입니다.');
      return;
    }
    this.dialog.open(TerminalLog, {
      data: { containerId: containerId },
      width: '800px',
      height: '600px',
      panelClass: 'custom-terminal-dialog'
    });
  }

  // 새로고침 버튼 등을 위해 제공
  refresh() {
    this.loadRuns(this.selectedExpId());
  }

  subscribeToUpdates() {
    this.eventSource = new EventSource(`${this.apiUrl}/train/status-stream`);

    this.eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('서버로부터 상태 업데이트 수신:', data);

      // 1. 특정 런의 상태가 바뀌었다는 신호를 받으면 리스트만 다시 불러옴
      if (data.event === 'status_changed' || data.event === 'started') {
        this.refresh(); // 기존의 리프레시 로직 재사용
        this.notificationService.showInfo(`작업 상태 변경: ${data.status}`);
      }
    };

    this.eventSource.onerror = () => {
      console.error('SSE 연결 끊김. 재연결 시도...');
      this.eventSource?.close();
      // 필요 시 재연결 로직 추가
    };
  }

  // 3. 새 창으로 열기 함수
  openMlflowDetail(runId: string) {
    const experimentId = this.selectedExpId();
    // MLflow UI가 실행 중인 주소 (5000 포트)
    const mlflowHost = 'http://localhost:5000';
    const url = `${mlflowHost}/#/experiments/${experimentId}/runs/${runId}`;
    window.open(url, '_blank');
  }

  navigateToRunDetail(runId: string) {
    this.router.navigate(['/models/run', runId], {
      queryParams: { expId: this.selectedExpId() }
    });
  }

}
