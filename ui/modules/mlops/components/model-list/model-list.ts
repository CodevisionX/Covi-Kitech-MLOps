import { Component, computed, effect, inject, NgZone, OnDestroy, OnInit, signal } from '@angular/core';
import { Jobs } from '../../services/apis/job';
import { ActivatedRoute, Router } from '@angular/router';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { IJob } from '../../services/apis/models/job.model';
import { Subject, Subscription, forkJoin } from 'rxjs';
import { debounceTime } from 'rxjs/operators';
import { Notification } from '../../services/notification';
import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';
import { TerminalLog } from '../dialogs/terminal-log/terminal-log';
import { IProject } from '../../services/apis/models/project.model';
import { Project } from '../../services/apis/project';
import { METRIC_LABELS, MODEL_CONFIGS, TASK_NAMES, isLegacyJob, modelTask, modelsForTask, sortModels } from '../../configs/model-config';
import { DatasetApi } from '../../services/apis/dataset';
import { ImportModelDialog, filesFromDrop } from '../dialogs/import-model/import-model';
import { Experiment } from '../../services/apis/experiment';
import { TrainingStatusDialog } from '../dialogs/training-status/training-status';

@Component({
  selector: 'app-model-list',
  standalone: false,
  templateUrl: './model-list.html',
  styleUrl: './model-list.scss',
})
export class ModelList implements OnInit, OnDestroy {

  private jobService = inject(Jobs);
  private projectService = inject(Project);
  private notificationService = inject(Notification);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private dialog = inject(MatDialog);
  private ngZone = inject(NgZone);
  private datasetApi = inject(DatasetApi);
  private experimentApi = inject(Experiment);

  /** 데이터셋 버전 id -> 'name:vN' */
  datasetNames = signal<Record<number, string>>({});

  projects = signal<IProject[]>([]);
  allActiveJobs = signal<IJob[]>([]);
  allHistoryJobs = signal<IJob[]>([]);

  selectedProjectId = signal<number | null>(null);
  selectedVariant = signal<string | null>(null);
  isLoading = signal<boolean>(false);

  private readonly dummyRows = new Array(5).fill({});

  displayActiveJobs = computed(() =>
    this.isLoading() ? this.dummyRows : this.filteredActiveJobs()
  );

  displayHistoryJobs = computed(() =>
    this.isLoading() ? this.dummyRows : this.filteredHistoryJobs()
  );

  // 1. 현재 로드된 전체 Job에서 존재하는 알고리즘 종류만 추출
  availableVariants = computed(() => {
    const activeVariants = this.allActiveJobs().map(j => j.model_variant);
    const historyVariants = this.allHistoryJobs().map(j => j.model_variant);
    const combined = [...new Set([...activeVariants, ...historyVariants])];
    return sortModels(combined);
  });

  /** 탭을 검출 / 인식 / 시계열 묶음으로 보여 줍니다 */
  variantGroups = computed(() => {
    const groups: { task: string; label: string; variants: string[] }[] = [];
    for (const v of this.availableVariants()) {
      const task = modelTask(v) ?? 'etc';
      let g = groups.find(x => x.task === task);
      if (!g) groups.push(g = { task, label: TASK_NAMES[task] ?? '기타', variants: [] });
      g.variants.push(v);
    }
    return groups;
  });

  // 2. 선택된 탭(Variant)에 따라 필터링된 데이터 제공
  filteredActiveJobs = computed(() => {
    const variant = this.selectedVariant();
    return variant ? this.allActiveJobs().filter(j => j.model_variant === variant) : this.allActiveJobs();
  });

  filteredHistoryJobs = computed(() => {
    const variant = this.selectedVariant();
    return variant ? this.allHistoryJobs().filter(j => j.model_variant === variant) : this.allHistoryJobs();
  });

  bestJob = computed(() => {
    const history = this.filteredHistoryJobs().filter(j => j.status === 'FINISHED' && j.metrics);
    const variant = this.selectedVariant();
    const metric = variant ? MODEL_CONFIGS[variant]?.bestMetric : undefined;
    if (metric) {
      // 신규 모델: 설정된 지표가 있는 학습만 비교 (업로드 모델은 학습 지표가 없어 제외)
      const scored = history.filter(j => j.metrics?.[metric.key] !== undefined);
      if (scored.length === 0) return null;
      return scored.reduce((prev, cur) => {
        const a = prev.metrics![metric.key], b = cur.metrics![metric.key];
        return (metric.higher ? b > a : b < a) ? cur : prev;
      });
    }
    if (history.length === 0) return null;

    return history.reduce((prev, current) => {
      const variant = current.model_variant;
      
      if (variant === '1D-CNN') {
        const prevLoss = prev.metrics?.['train_loss'] ?? Infinity;
        const currentLoss = current.metrics?.['train_loss'] ?? Infinity;
        return currentLoss < prevLoss ? current : prev;
      }

      else {
        const getScore = (job: IJob) =>
          job.metrics?.['metrics/mAP50(B)'] ??
          job.metrics?.['metrics/mAP50B'] ??
          job.metrics?.['metrics/mAP50_B'] ??
          job.metrics?.['mAP50(B)'] ?? 0;

        return getScore(current) > getScore(prev) ? current : prev;
      }
    });
  });

  /** 최고 모델 카드에 보일 지표 */
  bestMetricView = computed(() => {
    const best = this.bestJob();
    if (!best) return null;
    const metric = MODEL_CONFIGS[best.model_variant]?.bestMetric;
    if (metric) return { label: metric.label, value: best.metrics?.[metric.key] ?? 0 };
    if (best.model_variant === '1D-CNN') return { label: 'Train Loss', value: best.metrics?.['train_loss'] ?? 0 };
    return { label: 'mAP@0.5', value: best.metrics?.['metrics/mAP50_B'] || 0 };
  });

  bestJobId = computed(() => this.bestJob()?.id || null);

  /** 최고 성적 카드 아래쪽 정보: 검증 성능 / 테스트 성능 / 학습 설정 */
  bestDetails = computed(() => {
    const best = this.bestJob();
    if (!best) return [];
    const main = MODEL_CONFIGS[best.model_variant]?.bestMetric?.key;
    const pick = (prefix: string) => Object.entries(best.metrics ?? {})
      .filter(([k]) => k.startsWith(prefix) && k !== main)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => {
        const name = k.slice(prefix.length);
        return { label: METRIC_LABELS[name] || name, value: this.fmtNum(v) };
      });
    const params = Object.entries(best.params ?? {})
      .map(([k, v]) => ({ label: k, value: String(v) }));
    return [
      { title: '검증 성능', items: pick('best_val/') },
      { title: '테스트 성능', items: pick('test/') },
      { title: '학습 설정', items: params },
    ].filter(g => g.items.length);
  });

  private fmtNum(v: number): string {
    if (!Number.isFinite(v)) return '-';
    return Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(4);
  }

  /** 학습에 걸린 시간 'H:MM:SS' */
  duration(job: IJob): string | null {
    if (!job.started_at || !job.finished_at) return null;
    const sec = Math.max(0, Math.floor((new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000));
    const p = (n: number) => String(n).padStart(2, '0');
    return `${Math.floor(sec / 3600)}:${p(Math.floor(sec / 60) % 60)}:${p(sec % 60)}`;
  }

  activeDisplayedColumns = ['modelInfo', 'status', 'progress', 'startedAt', 'elapsed', 'statusView', 'cancel'];
  historyDisplayedColumns = computed(() => {
    const variant = this.selectedVariant();
    
    if (variant && this.hasDetail(variant)) {
      return ['modelInfo', 'status', 'startTime', 'dashboard', 'management', 'actions'];
    }
    
    // 그 외의 모델(XGBoost 등)일 경우 'management'(분석 및 배포) 제외
    return ['modelInfo', 'status', 'startTime', 'dashboard', 'actions'];
  });

  hasDetail(variant: string): boolean {
    return variant === '1D-CNN' || variant === 'YOLOv8' || !!MODEL_CONFIGS[variant]?.pyfunc;
  }

  bestMetricOf(job: IJob): { label: string; value: number } | null {
    const metric = MODEL_CONFIGS[job.model_variant]?.bestMetric;
    const value = metric ? job.metrics?.[metric.key] : undefined;
    return metric && value !== undefined ? { label: metric.label, value } : null;
  }

  /** 모델 파일 업로드를 지원하는 모델 (검출·인식) */
  readonly importable = [...modelsForTask('detection'), ...modelsForTask('recognition')];

  isPyfunc(variant: string | null): boolean {
    return !!variant && !!MODEL_CONFIGS[variant]?.pyfunc;
  }

  private sseSubscription: Subscription | null = null;
  private currentLogDialogRef: MatDialogRef<TerminalLog> | null = null;
  private refreshTrigger = new Subject<void>();
  /** 실행 중인 학습이 있는 동안 진행도를 갱신하는 타이머 (화면 깜빡임 없이 실행 중 목록만 다시 받음) */
  private progressTimer: ReturnType<typeof setInterval> | null = null;
  private static readonly PROGRESS_POLL_MS = 1000;
  private pollInFlight = false;
  /** 소요 시간 표시용 현재 시각 (1초마다 갱신) */
  now = signal(Date.now());

  constructor() {
    this.refreshTrigger.pipe(debounceTime(500)).subscribe(() => this.refreshJobs());
  }

  ngOnInit(): void {
    this.isLoading.set(true);

    this.loadProjects();
    this.subscribeToJobUpdates();
    this.progressTimer = setInterval(() => {
      this.now.set(Date.now());
      this.pollActiveProgress();
    }, ModelList.PROGRESS_POLL_MS);

    this.route.queryParams.subscribe(params => {
      if (params['projectId']) {
        this.selectedProjectId.set(+params['projectId']);
      }
      if (params['variant']) {
        this.selectedVariant.set(params['variant']);
      }

      if (this.selectedProjectId()) {
        this.refreshJobs();
      }
    });
  }

  ngOnDestroy(): void {
    if (this.progressTimer) clearInterval(this.progressTimer);
    if (this.sseSubscription) {
      console.log('sse 구독을 해제하고 연결을 종료합니다.');
      this.sseSubscription.unsubscribe();
    }
  }

  loadProjects() {
    this.isLoading.set(true);

    this.projectService.getProjects().subscribe({
      next: (project) => {
        this.projects.set(project);

        if (project.length > 0) {
          if (!this.selectedProjectId()) {
            this.onProjectChange(project[0].id);
          }
        } else {
          this.isLoading.set(false);
        }
      },
      error: (err) => {
        this.notificationService.showError('프로젝트 목록을 불러오지 못했습니다.');
        this.isLoading.set(false);
      }
    });
  }

  refreshJobs() {
    const projectId = this.selectedProjectId();
    if (!projectId) return;

    console.log(`Project ${projectId}의 최신 데이터를 불러오는 중...`);
    this.isLoading.set(true);

    forkJoin({
      active: this.jobService.getActiveJobs(projectId),
      history: this.jobService.getJobHistory(0, 50, projectId)
    }).subscribe({
      next: (res) => {
        this.allActiveJobs.set(res.active);
        this.allHistoryJobs.set(res.history);
        this.loadDatasetNames(projectId);

        if (!this.selectedVariant() && this.availableVariants().length > 0) {
          this.onVariantChange(this.availableVariants()[0]);
        }
        this.isLoading.set(false);
      },
      error: (err) => {
        this.notificationService.showError(err);
        this.isLoading.set(false);
      }
    });
  }

  private pollActiveProgress() {
    const projectId = this.selectedProjectId();
    if (!projectId || this.isLoading() || document.hidden) return;
    if (this.pollInFlight || !this.allActiveJobs().some(j => j.status === 'RUNNING')) return;
    this.pollInFlight = true;
    this.jobService.getActiveJobs(projectId).subscribe({
      next: active => {
        if (projectId === this.selectedProjectId()) this.allActiveJobs.set(active);
        this.pollInFlight = false;
      },
      error: () => { this.pollInFlight = false; },
    });
  }

  private loadDatasetNames(projectId: number) {
    this.datasetApi.listVersions({ project_id: projectId }).subscribe({
      next: list => this.datasetNames.set(
        Object.fromEntries(list.map(v => [v.id, `${v.name}:v${v.version ?? '-'}`]))),
      error: () => { },
    });
  }

  uploadDragOver = signal(false);

  onUploadDragOver(e: DragEvent) {
    e.preventDefault();
    this.uploadDragOver.set(true);
  }

  /** 버튼에 끌어다 놓은 파일·폴더로 업로드 창을 엽니다 */
  async onUploadDrop(e: DragEvent) {
    e.preventDefault();
    this.uploadDragOver.set(false);
    if (!this.selectedProjectId() || !e.dataTransfer) return;
    this.openImportDialog(await filesFromDrop(e.dataTransfer));
  }

  /** 모델 파일(.pt / inference.*)을 올려 학습 결과처럼 쓸 수 있게 합니다. */
  openImportDialog(files?: File[]) {
    const projectId = this.selectedProjectId();
    if (!projectId) return;
    const variant = this.selectedVariant();
    this.dialog.open(ImportModelDialog, {
      width: '560px',
      // 파일 선택창의 '열기' 클릭이 배경으로 전달되어 모달이 닫히는 일을 막습니다 (취소 버튼으로만 닫기)
      disableClose: true,
      data: { projectId, variant: this.importable.includes(variant || '') ? variant : this.importable[0], files },
    }).afterClosed().subscribe(job => {
      if (!job) return;
      this.refreshJobs();
      if (job.model_variant !== this.selectedVariant()) this.onVariantChange(job.model_variant);
    });
  }

  subscribeToJobUpdates() {
    console.log('sse 실시간 업데이트 구독을 시작합니다.');
    this.sseSubscription = this.jobService.getJobUpdates().subscribe({
      next: (event: any) => {
        console.log('SSE Event received:', event);

        const data = event.data;
        // 프로젝트 아이디가 다르면 무시
        if (data.project_id != this.selectedProjectId()) return;

        this.ngZone.run(() => {
          // [수정] 조건문을 각각 독립적으로 검사합니다.
          if (event.event === 'new_job') {
            const exists = this.allActiveJobs().some(j => j.id === data.job_id);
            if (!exists) {
              console.log('신규 작업 감지 -> 리스트 갱신');
              this.refreshTrigger.next();
            }
          }

          // [수정] job_status는 별도의 if 문으로 처리하거나 else if로 뺍니다.
          if (event.event === 'job_status') {
            console.log('상태 변경 감지(KILLED/FINISHED 등) -> 리스트 갱신');
            this.refreshTrigger.next();
          }
        });
      },
      error: (err) => console.error('SSE Error:', err)
    });
  }

  onProjectChange(projectId: number) {
    this.selectedVariant.set(null);
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { projectId: projectId, variant: null },
      queryParamsHandling: 'merge' // 기존 다른 쿼리 파라미터 유지
    });
  }

  onVariantChange(variant: string) {
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { variant: variant },
      queryParamsHandling: 'merge'
    });
  }

  onCancelJob(jobId: number) {
    if (!confirm('정말 이 작업을 취소하시겠습니까?')) return;

    this.allActiveJobs.update(jobs =>
      jobs.map(j => {
        if (j.id === jobId) {
          return { ...j, status: 'CANCELLING' as any };
        }
        return j;
      })
    );

    this.jobService.cancelJob(jobId).subscribe({
      next: () => {
        this.notificationService.showSuccess('작업 취소 요청됨');
        // SSE가 곧 job_status 보내줄 것이므로 수동 갱신 안 해도 됨
      },
      error: (err) => {
        this.notificationService.showError('취소 실패');
        this.refreshJobs();
      }
    });
  }

  /** 실행 중인 학습의 현황(진행도, 실시간 차트, 로그) 모달 */
  openStatus(job: IJob) {
    this.dialog.open(TrainingStatusDialog, {
      data: { job },
      width: '1280px', maxWidth: '96vw', height: '92vh',
      panelClass: 'training-status-panel', autoFocus: false,
    });
  }

  openLogDialog(job: IJob) {
    if (!job || !job.id) return;

    this.currentLogDialogRef = this.dialog.open(TerminalLog, {
      data: {
        id: job.id,
        status: job.status,
        type: 'job'
      },
      width: '800px',
      height: '600px',
      panelClass: 'custom-terminal-dialog',
      disableClose: false
    });

    this.currentLogDialogRef.afterClosed().subscribe(() => this.currentLogDialogRef = null);
  }

  openMlflowDetail(job: IJob) {
    if (!job.run_id || !job.experiment_id) {
      this.notificationService.showError('MLflow 정보를 찾을 수 없습니다.');
      return;
    }
    // MLflow UI URL (환경변수나 설정에서 가져오는 것이 좋음)
    const mlflowUrl = `${this.experimentApi.mlflowUiUrl}/#/experiments/${job.experiment_id}/runs/${job.run_id}`;
    window.open(mlflowUrl, '_blank');
  }

  navigateToRunDetail(job: IJob) {
    if (!job.run_id) return;

    const pathMap: Record<string, string> = {
      'YOLOv8': 'yolo',
      '1D-CNN': 'cnn'
    };

    // v1 방식 기존 기록은 기존 상세 화면, 그 외(등록 데이터셋·가져온 모델)는 새 상세 화면
    const segment = this.isPyfunc(job.model_variant) && !isLegacyJob(job) ? 'v2' : (pathMap[job.model_variant] || 'yolo');

    this.router.navigate(['/dashboard/models/run', segment, job.run_id], {
      queryParams: {
        projectId: job.project_id,
        expId: job.experiment_id, // 상세 페이지에서도 MLflow API 호출을 위해 필요
        jobId: job.id
      }
    });
  }

  /** 'YYYY-MM-DD HH:mm:ss' */
  formatClock(dateStr?: string | null): string {
    if (!dateStr) return '-';
    const d = new Date(dateStr);
    const p = (n: number) => String(n).padStart(2, '0');
    const time = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${time}`;
  }

  /** 시작부터 지금까지 'H:MM:SS' (1초마다 갱신) */
  elapsed(dateStr?: string | null): string {
    if (!dateStr) return '-';
    const sec = Math.max(0, Math.floor((this.now() - new Date(dateStr).getTime()) / 1000));
    const p = (n: number) => String(n).padStart(2, '0');
    return `${Math.floor(sec / 3600)}:${p(Math.floor(sec / 60) % 60)}:${p(sec % 60)}`;
  }

  getRelativeTime(dateStr?: string | null): string {
    if (!dateStr) return '-';
    return formatDistanceToNow(new Date(dateStr), { addSuffix: true, locale: ko });
  }


}