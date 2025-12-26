import { Component, computed, effect, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { TerminalLog } from '../dialogs/terminal-log/terminal-log';
import { ActivatedRoute, Router } from '@angular/router';
import { finalize, forkJoin, Subscription } from 'rxjs';
import { Notification } from '../../services/notification';
import { IMLflowRun, IExperiment } from '../../services/apis/models/experiment.model';
import { ITrainingJob } from '../../services/apis/models/training.model';
import { Experiment } from '../../services/apis/experiment';
import { Training } from '../../services/apis/training';
import { Model } from '../../services/model';

@Component({
  selector: 'app-model-list',
  standalone: false,
  templateUrl: './model-list.html',
  styleUrl: './model-list.scss',
})
export class ModelList implements OnInit, OnDestroy {
  private readonly router = inject(Router);
  private readonly experiment = inject(Experiment);
  private readonly training = inject(Training);
  private modelService = inject(Model);
  private dialog = inject(MatDialog);
  private readonly route = inject(ActivatedRoute);
  private notificationService = inject(Notification);

  private currentLogDialogRef: MatDialogRef<TerminalLog> | null = null;
  private statusSubscription: Subscription | null = null;

  activeDisplayedColumns: string[] = ['modelInfo', 'status', 'startTime', 'dashboard', 'actions', 'cancel'];
  historyDisplayedColumns: string[] = ['modelInfo', 'status', 'startTime', 'dashboard', 'management', 'actions'];

  // 1. 상태 관리 Signal
  dbJobs = signal<ITrainingJob[]>([]);
  mlflowRuns = signal<IMLflowRun[]>([]);
  dbHistoryList = signal<ITrainingJob[]>([]);

  experiments = signal<IExperiment[]>([]);
  selectedExpId = signal<string>('');
  isLoading = signal<boolean>(false);

  bestRunId = computed(() => {
    return this.modelService.calculateBestRunId(this.mlflowRuns());
  });

  // 2. 상태별 필터링 (Computed)
  activeJobs = computed(() => {
    const currentExp = this.experiments().find(e => e.experiment_id === this.selectedExpId());
    const algoName = currentExp?.name.replace('_Experiments', '');

    return this.dbJobs()
      .filter(job =>
        job.model_variant === algoName &&
        (job.status === 'PENDING' || job.status === 'RUNNING') // CANCELLED는 여기서 빠짐
      )
      .map(job => ({
        ...job,
        displayTime: new Date(job.created_at).getTime(),
        containerId: job.container_id
      }))
      .sort((a, b) => b.displayTime - a.displayTime);
  });

  // 2. 학습 이력 정렬 및 시간 통일 수정
  historyJobs = computed(() => {
    const currentExp = this.experiments().find(e => e.experiment_id === this.selectedExpId());
    const algoName = currentExp?.name.replace('_Experiments', '');

    const mlflowHistory = this.mlflowRuns().filter(run =>
      run.status !== 'RUNNING' && run.status !== 'SCHEDULED'
    );

    const dbHistory = this.dbHistoryList().filter(job =>
      job.model_variant === algoName &&
      (job.status === 'FINISHED' || job.status === 'FAILED' || job.status === 'CANCELLED') // 취소 건 포함
    );

    // MLflow 데이터 정규화
    const mergedHistory = mlflowHistory.map(run => {
      const matchingDbJob = dbHistory.find(job => job.run_id === run.run_id);
      return {
        ...run,
        displayTime: (run as any).start_time,
        // 중요: HTML에서 쓸 필드명을 containerId로 통일
        containerId: run.tags?.container_id || matchingDbJob?.container_id
      };
    });

    // DB 전용(취소 건) 데이터 정규화
    const mlflowRunIds = new Set(mlflowHistory.map(r => r.run_id));
    const orphanDbJobs = dbHistory
      .filter(job => !job.run_id || !mlflowRunIds.has(job.run_id))
      .map(job => ({
        ...job,
        displayTime: new Date(job.updated_at || job.created_at).getTime(),
        containerId: job.container_id // 통일
      }));

    return [...mergedHistory, ...orphanDbJobs].sort((a: any, b: any) => {
      return (b.displayTime || 0) - (a.displayTime || 0);
    });
  });

  constructor() {
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
    this.statusSubscription?.unsubscribe();
  }

  loadInitialData() {
    this.isLoading.set(true);
    this.experiment.getAll().subscribe({
      next: (exps) => {
        this.experiments.set(exps);
        const queryExpId = this.route.snapshot.queryParamMap.get('expId');
        if (queryExpId && exps.some(e => e.experiment_id === queryExpId)) {
          this.selectedExpId.set(queryExpId);
        } else if (exps.length > 0) {
          this.selectedExpId.set(exps[0].experiment_id);
        } else {
          this.isLoading.set(false);
        }
      },
      error: () => {
        this.notificationService.showError('실험 목록 로드 실패');
        this.isLoading.set(false);
      }
    });
  }

  loadRuns(expId: string) {
    this.isLoading.set(true);
    this.experiment.getRunsByExperiment(expId).subscribe({
      next: (runs) => {
        this.mlflowRuns.set(runs);
        this.isLoading.set(false);
      },
      error: () => {
        this.isLoading.set(false);
        this.notificationService.showError('내역 로드 실패');
      }
    });
  }

  onAlgorithmChange(expId: string) {
    this.selectedExpId.set(expId);
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { expId: expId },
      queryParamsHandling: 'merge',
    });
  }

  getRelativeTime(time: number | string) {
    if (!time) return '-';
    const date = typeof time === 'string' ? new Date(time).getTime() : time;
    const now = Date.now();
    const diff = Math.floor((now - date) / 1000);

    if (diff < 60) return '방금 전';
    if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
    return new Date(date).toLocaleString('ko-KR', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false
    });
  }

  refresh() {
    this.isLoading.set(true);
    const expId = this.selectedExpId();
    const requests: any = {
      active: this.training.getActiveJobs(),
      history: this.training.getHistory()
    };
    if (expId) requests.mlflow = this.experiment.getRunsByExperiment(expId);

    forkJoin(requests).pipe(finalize(() => this.isLoading.set(false))).subscribe({
      next: (res: any) => {
        this.dbJobs.set(res.active);
        this.dbHistoryList.set(res.history);
        if (res.mlflow) this.mlflowRuns.set(res.mlflow);
      },
      error: () => this.notificationService.showError('데이터 로드 실패')
    });
  }

  subscribeToUpdates() {
    this.statusSubscription?.unsubscribe();
    this.statusSubscription = this.training.getStatusStream().subscribe({
      next: (data) => {
        if (data.event === 'container_created') {
          this.dbJobs.update(jobs => jobs.map(j => j.id === data.job_id ? { ...j, container_id: data.container_id } : j));
        }
        if (data.event === 'job_queued' || data.event === 'status_changed') {
          this.refresh();
          if (data.status !== 'RUNNING' && data.status !== 'PENDING') {
            this.closeLogDialogIfMatch(data.job_id);
          }
          if (data.status === 'RUNNING') {
            this.notificationService.showInfo(`학습이 시작되었습니다! (Job ID: ${data.job_id})`);
          }
        }
      }
    });
  }

  openMlflowDetail(runId: string) {
    const url = `http://localhost:5000/#/experiments/${this.selectedExpId()}/runs/${runId}`;
    window.open(url, '_blank');
  }

  navigateToRunDetail(runId: string) {
    this.router.navigate(['/dashboard/models/run', runId], {
      queryParams: { expId: this.selectedExpId() }
    });
  }

  onCancelJob(jobId: number) {
    if (!confirm('정말로 취소하시겠습니까?')) return;

    const targetJob = this.dbJobs().find(j => j.id === jobId);

    if (targetJob) {
      // 1. 진행 중 목록에서 제거
      this.dbJobs.update(jobs => jobs.filter(j => j.id !== jobId));

      // 2. 이력 목록으로 즉시 이동 (상태만 CANCELLED로 변경해서 넣기)
      this.dbHistoryList.update(history => [
        { ...targetJob, status: 'CANCELLED', updated_at: new Date().toISOString() },
        ...history
      ]);
    }

    // 3. 서버에 요청 (나머지는 SSE가 알아서 최종 정합성을 맞춰줍니다)
    this.training.cancel(jobId).subscribe({
      error: (err) => {
        this.notificationService.showError('취소 요청 실패');
        this.refresh(); // 실패했을 때만 다시 데이터를 불러와서 복구
      }
    });
  }

  private closeLogDialogIfMatch(jobId: number) {
    if (this.currentLogDialogRef) {
      this.currentLogDialogRef.close();
      this.currentLogDialogRef = null;
    }
  }

  openLogDialog(containerId: string) {
    if (!containerId) return;
    this.currentLogDialogRef = this.dialog.open(TerminalLog, {
      data: { containerId }, width: '800px', height: '600px', panelClass: 'custom-terminal-dialog'
    });
    this.currentLogDialogRef.afterClosed().subscribe(() => this.currentLogDialogRef = null);
  }
}