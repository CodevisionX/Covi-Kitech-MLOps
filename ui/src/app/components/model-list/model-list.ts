import { Component, computed, effect, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { Api, Experiment, MLflowRun, TrainingJob } from '../../core/services/api';
import { MatDialog } from '@angular/material/dialog';
import { TerminalLog } from '../dialogs/terminal-log/terminal-log';
import { Notification } from '../../core/services/notification';
import { ActivatedRoute, Router } from '@angular/router';
import { environment } from '../../../environments/environment';
import { finalize, forkJoin } from 'rxjs';

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

  activeDisplayedColumns: string[] = ['modelInfo', 'status', 'startTime', 'dashboard', 'actions', 'cancel'];
  historyDisplayedColumns: string[] = ['modelInfo', 'status', 'startTime', 'dashboard', 'management', 'actions'];

  // 1. 상태 관리 Signal
  dbJobs = signal<TrainingJob[]>([]); // 진행 중인 작업 (PENDING, RUNNING)
  mlflowRuns = signal<MLflowRun[]>([]); // MLflow에서 가져온 실행 이력
  dbHistoryList = signal<TrainingJob[]>([]); // 취소/완료된 작업 (CANCELLED, FINISHED, FAILED)

  experiments = signal<Experiment[]>([]);
  selectedExpId = signal<string>(''); // 선택된 실험 ID
  isLoading = signal<boolean>(false);

  // 2. 상태별 필터링 (Computed)
  activeJobs = computed(() => {
    const currentExp = this.experiments().find(e => e.experiment_id === this.selectedExpId());
    const algoName = currentExp?.name.replace('_Experiments', '');

    return this.dbJobs().filter(job => job.model_variant === algoName);
  });

  // 1. DB에서 가져온 작업 중 완료/실패/취소된 것들을 따로 필터링
  dbHistoryJobs = computed(() => {
    return this.dbJobs().filter(job =>
      job.status === 'FINISHED' || job.status === 'FAILED' || job.status === 'CANCELLED'
    );
  });

  // 2. 최종 히스토리 목록 (MLflow 데이터 + DB 취소 데이터 합치기)
  // model-list.ts 수정 제안
  historyJobs = computed(() => {
    const currentExp = this.experiments().find(e => e.experiment_id === this.selectedExpId());
    const algoName = currentExp?.name.replace('_Experiments', '');

    const mlflowHistory = this.mlflowRuns().filter(run =>
      run.status !== 'RUNNING' && run.status !== 'SCHEDULED'
    );

    const dbHistory = this.dbHistoryList().filter(job => job.model_variant === algoName);

    // 병합 로직 개선
    const mergedHistory = mlflowHistory.map(run => {
      // 같은 run_id를 가진 DB 작업을 찾습니다.
      const matchingDbJob = dbHistory.find(job => job.run_id === run.run_id);
      return {
        ...run,
        // MLflow 태그에 없더라도 DB에 container_id가 있다면 보완해줍니다.
        container_id: run.tags?.container_id || matchingDbJob?.container_id
      };
    });

    // MLflow에 기록되지 않은 (주로 취소된) DB 작업들 추가
    const mlflowRunIds = new Set(mlflowHistory.map(r => r.run_id));
    const orphanDbJobs = dbHistory.filter(job => !job.run_id || !mlflowRunIds.has(job.run_id));

    return [...mergedHistory, ...orphanDbJobs].sort((a, b) => {
      const timeA = ('start_time' in a) ? (a.start_time as number) : new Date((a as TrainingJob).updated_at || (a as TrainingJob).created_at).getTime();
      const timeB = ('start_time' in b) ? (b.start_time as number) : new Date((b as TrainingJob).updated_at || (b as TrainingJob).created_at).getTime();
      return timeB - timeA;
    });
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
    this.refresh();
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
        this.mlflowRuns.set(runs);
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
  getRelativeTime(time: number | string) {
    if (!time) return '-';

    let date: number;
    if (typeof time === 'string') {
      // 만약 서버에서 오는 시간 문자열 끝에 타임존 정보가 없다면 강제로 보정할 수 있습니다.
      // 하지만 가장 좋은 방법은 서버에서 ISO 포맷(Z 포함)으로 보내주는 것입니다.
      date = new Date(time).getTime();
    } else {
      date = time;
    }

    const now = Date.now();
    const diff = Math.floor((now - date) / 1000);

    if (diff < 60) return '방금 전';
    if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;

    // 한국 날짜 형식으로 명시적 변환
    return new Date(date).toLocaleString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false // 24시간 형식 선호 시
    });
  }

  // 새로고침 버튼 등을 위해 제공
  refresh() {
    this.isLoading.set(true);
    const expId = this.selectedExpId();

    // 1. 병렬로 실행할 요청들을 정의합니다.
    const requests: any = {
      active: this.apiService.getActiveJobs(),
      history: this.apiService.getJobHistory()
    };

    // 실험 ID가 있으면 MLflow 실행 내역도 포함합니다.
    if (expId) {
      requests.mlflow = this.apiService.getRunsByExperiment(expId);
    }

    // 2. forkJoin으로 모든 요청이 끝날 때까지 기다립니다.
    forkJoin(requests)
      .pipe(
        // 성공/실패 여부와 상관없이 마지막에 로딩을 끕니다.
        finalize(() => this.isLoading.set(false))
      )
      .subscribe({
        next: (res: any) => {
          this.dbJobs.set(res.active);
          this.dbHistoryList.set(res.history);
          if (res.mlflow) {
            this.mlflowRuns.set(res.mlflow);
          }
        },
        error: (err) => {
          console.error('데이터 로드 실패:', err);
          this.notificationService.showError('데이터를 불러오는 중 오류가 발생했습니다.');
        }
      });
  }

  subscribeToUpdates() {
    this.eventSource = new EventSource(`${this.apiUrl}/train/status-stream`);

    this.eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      // job_queued(대기열 추가)나 status_changed(상태 변경) 시 즉시 리프레시
      if (data.event === 'job_queued' || data.event === 'status_changed') {
        this.refresh();
        if (data.status === 'RUNNING') {
          this.notificationService.showInfo(`학습이 시작되었습니다! (Job ID: ${data.job_id})`);
        }
      }
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

  onCancelJob(jobId: number) {
    if (confirm('정말로 이 학습 작업을 취소하시겠습니까?')) {
      this.apiService.cancelJob(jobId).subscribe({
        next: (res) => {
          this.notificationService.showInfo(res.message);
          this.refresh(); // 리스트 갱신
        },
        error: () => this.notificationService.showError('취소 요청 실패')
      });
    }
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

}