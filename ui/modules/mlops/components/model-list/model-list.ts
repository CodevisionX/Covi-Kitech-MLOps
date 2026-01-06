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
    return combined.sort();
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
    if (history.length === 0) return null;

    return history.reduce((prev, current) => {
      const getScore = (job: IJob) =>
        job.metrics?.['metrics/mAP50(B)'] ??
        job.metrics?.['metrics/mAP50B'] ??
        job.metrics?.['metrics/mAP50_B'] ??
        job.metrics?.['mAP50(B)'] ?? 0;

      return getScore(current) > getScore(prev) ? current : prev;
    });
  });
  bestJobId = computed(() => this.bestJob()?.id || null);

  activeDisplayedColumns = ['modelInfo', 'status', 'startTime', 'dashboard', 'actions', 'cancel'];
  historyDisplayedColumns = ['modelInfo', 'status', 'startTime', 'dashboard', 'management', 'actions'];

  private sseSubscription: Subscription | null = null;
  private currentLogDialogRef: MatDialogRef<TerminalLog> | null = null;
  private refreshTrigger = new Subject<void>();

  constructor() {
    this.refreshTrigger.pipe(debounceTime(500)).subscribe(() => this.refreshJobs());
  }

  ngOnInit(): void {
    this.isLoading.set(true);

    this.loadProjects();
    this.subscribeToJobUpdates();

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

  subscribeToJobUpdates() {
    console.log('sse 실시간 업데이트 구독을 시작합니다.');
    this.sseSubscription = this.jobService.getJobUpdates().subscribe({
      next: (event: any) => {
        // event 구조: { event: 'job_status', data: { project_id: 1, ... } }
        console.log('SSE Event received:', event);

        // 백엔드에서 평탄화했으므로 event.data.project_id로 바로 접근 가능
        const data = event.data;

        if (event.event === 'job_status' && data.project_id == this.selectedProjectId()) {
          this.ngZone.run(() => {
            console.log('상태 변경 감지, 리스트 갱신');
            this.refreshTrigger.next();
          });
        }

        if (event.event === 'new_job' && data.project_id == this.selectedProjectId()) {
          this.ngZone.run(() => {
            console.log('새 작업 감지, 리스트 갱신');
            this.refreshTrigger.next();
          });
        }
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
    const mlflowUrl = `http://localhost:15000/#/experiments/${job.experiment_id}/runs/${job.run_id}`;
    window.open(mlflowUrl, '_blank');
  }

  navigateToRunDetail(job: IJob) {
    if (!job.run_id) return;
    this.router.navigate(['/dashboard/models/run', job.run_id], {
      queryParams: {
        projectId: job.project_id,
        expId: job.experiment_id, // 상세 페이지에서도 MLflow API 호출을 위해 필요
        jobId: job.id
      }
    });
  }

  getRelativeTime(dateStr?: string | null): string {
    if (!dateStr) return '-';
    return formatDistanceToNow(new Date(dateStr), { addSuffix: true, locale: ko });
  }


}