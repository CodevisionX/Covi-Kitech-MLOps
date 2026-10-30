import { Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { Router } from '@angular/router';
import { forkJoin } from 'rxjs';
import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';
import { EvaluationApi } from '../../services/apis/evaluation';
import { DatasetApi } from '../../services/apis/dataset';
import { Jobs } from '../../services/apis/job';
import { Project } from '../../services/apis/project';
import { Notification } from '../../services/notification';
import { IProject } from '../../services/apis/models/project.model';
import { IJob } from '../../services/apis/models/job.model';
import { IDatasetVersion } from '../../services/apis/models/dataset.model';
import {
  DEFAULT_EVALUATION_PARAMS, IEvaluation, IEvaluationParams,
} from '../../services/apis/models/evaluation.model';

const TERMINAL = ['FINISHED', 'FAILED'];

@Component({
  selector: 'app-evaluation-list',
  standalone: false,
  templateUrl: './evaluations.html',
  styleUrl: './evaluations.scss',
})
export class EvaluationList implements OnInit, OnDestroy {
  private readonly api = inject(EvaluationApi);
  private readonly datasetApi = inject(DatasetApi);
  private readonly jobs = inject(Jobs);
  private readonly projectService = inject(Project);
  private readonly notification = inject(Notification);
  private readonly router = inject(Router);

  projects = signal<IProject[]>([]);
  projectId = signal<number | null>(null);
  evaluations = signal<IEvaluation[]>([]);
  allJobs = signal<IJob[]>([]);
  versions = signal<IDatasetVersion[]>([]);
  isLoading = signal(false);
  isSubmitting = signal(false);
  showParams = signal(false);

  detJobId: number | null = null;
  recJobId: number | null = null;
  datasetId: number | null = null;
  name = '';
  params: IEvaluationParams = { ...DEFAULT_EVALUATION_PARAMS };

  detJobs = computed(() => this.finished('YOLO26'));
  recJobs = computed(() => this.finished('PP-OCRv6'));
  e2eVersions = computed(() => this.versions().filter(v => v.task === 'e2e' && v.status === 'READY'));
  versionMap = computed(() => new Map(this.versions().map(v => [v.id, v])));

  readonly columns = ['id', 'name', 'models', 'dataset', 'status', 'slotAcc', 'detect6', 'created', 'actions'];
  private timer: any = null;

  ngOnInit() {
    this.projectService.getProjects().subscribe({
      next: p => {
        this.projects.set(p);
        if (p.length) this.onProjectChange(p[0].id);
      },
      error: () => this.notification.showError('프로젝트 목록을 불러오지 못했습니다.'),
    });
  }

  ngOnDestroy() {
    this.stopPolling();
  }

  onProjectChange(id: number) {
    this.projectId.set(id);
    this.detJobId = this.recJobId = this.datasetId = null;
    this.isLoading.set(true);
    forkJoin({
      jobs: this.jobs.getJobHistory(0, 200, id),
      versions: this.datasetApi.listVersions({ project_id: id }),
    }).subscribe({
      next: ({ jobs, versions }) => {
        this.allJobs.set(jobs);
        this.versions.set(versions);
      },
      error: e => this.notification.showError(e.message),
    });
    this.loadEvaluations();
  }

  loadEvaluations() {
    const id = this.projectId();
    if (!id) return;
    this.api.list(id).subscribe({
      next: list => {
        this.evaluations.set([...list].sort((a, b) => b.id - a.id));
        this.isLoading.set(false);
        if (list.some(e => !TERMINAL.includes(e.status))) this.startPolling();
        else this.stopPolling();
      },
      error: e => {
        this.isLoading.set(false);
        this.notification.showError(e.message);
      },
    });
  }

  private startPolling() {
    if (!this.timer) this.timer = setInterval(() => this.loadEvaluations(), 3000);
  }

  private stopPolling() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  private finished(variant: string) {
    return this.allJobs()
      .filter(j => j.model_variant === variant && j.status === 'FINISHED' && j.run_id)
      .sort((a, b) => b.id - a.id);
  }

  jobLabel(job: IJob): string {
    const det = job.model_variant === 'YOLO26';
    const key = det ? 'best_val/mAP50-95' : 'best_val/acc';
    const v = job.metrics?.[key];
    const metric = `${det ? 'mAP50-95' : '정확도'} ${v === undefined || v === null ? '-' : v.toFixed(3)}`;
    const origin = job.tags?.['source'] === 'imported'
      ? `현장 모델${job.tags?.['import_name'] ? ' ' + job.tags['import_name'] : ''}`
      : this.trainedOn(job);
    return `#${job.id} · ${origin} · ${metric} · ${this.relTime(job.finished_at)}`;
  }

  trainedOn(job: IJob): string {
    if (!job.dataset_version_id) return '학습';
    const v = this.versionMap().get(job.dataset_version_id);
    return v ? `학습 데이터 ${v.name}:v${v.version}` : `학습 데이터 #${job.dataset_version_id}`;
  }

  versionLabel(id: number): string {
    const v = this.versionMap().get(id);
    return v ? `${v.name}:v${v.version}` : `#${id}`;
  }

  resetParams() {
    this.params = { ...DEFAULT_EVALUATION_PARAMS };
  }

  get canSubmit() {
    return !!(this.projectId() && this.detJobId && this.recJobId && this.datasetId) && !this.isSubmitting();
  }

  submit() {
    if (!this.canSubmit) return;
    this.isSubmitting.set(true);
    this.api.create({
      project_id: this.projectId()!,
      detection_job_id: this.detJobId!,
      recognition_job_id: this.recJobId!,
      dataset_version_id: this.datasetId!,
      name: this.name.trim() || undefined,
      params: this.params,
    }).subscribe({
      next: ev => {
        this.isSubmitting.set(false);
        this.notification.showSuccess(`평가를 시작했습니다 (ID: ${ev.id})`);
        this.router.navigate(['/dashboard/evaluations', ev.id]);
      },
      error: e => {
        this.isSubmitting.set(false);
        this.notification.showError(e.message);
      },
    });
  }

  open(ev: IEvaluation) {
    this.router.navigate(['/dashboard/evaluations', ev.id]);
  }

  remove(ev: IEvaluation, event: Event) {
    event.stopPropagation();
    const running = !TERMINAL.includes(ev.status);
    if (!confirm(`평가 #${ev.id}를 삭제할까요?${running ? ' 실행 중인 평가는 중단됩니다.' : ''}`)) return;
    this.api.delete(ev.id).subscribe({
      next: () => {
        this.notification.showSuccess('삭제했습니다.');
        this.loadEvaluations();
      },
      error: e => this.notification.showError(e.message),
    });
  }

  pct(v?: number | null): string {
    return v === undefined || v === null ? '-' : `${(v * 100).toFixed(1)}%`;
  }

  relTime(d?: string | null): string {
    return d ? formatDistanceToNow(new Date(d), { addSuffix: true, locale: ko }) : '-';
  }
}
