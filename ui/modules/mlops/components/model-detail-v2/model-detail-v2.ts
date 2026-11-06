import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { MatDialog } from '@angular/material/dialog';
import { ImageViewerDialog, ImageViewerData } from '../dialogs/image-viewer/image-viewer';
import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';
import { Experiment } from '../../services/apis/experiment';
import { Deployment } from '../../services/apis/deployment';
import { Jobs } from '../../services/apis/job';
import { IMLflowRun } from '../../services/apis/models/experiment.model';
import { IJob } from '../../services/apis/models/job.model';
import { Notification } from '../../services/notification';
import { METRIC_LABELS, isDetectionModel } from '../../configs/model-config';

interface MetricTile { key: string; label: string; value: number; }



/** YOLO26 / PP-OCRv6 학습(또는 업로드 모델) run 상세 */
@Component({
  selector: 'app-model-detail-v2',
  standalone: false,
  templateUrl: './model-detail-v2.html',
  styleUrl: './model-detail-v2.scss',
})
export class ModelDetailV2 implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  protected readonly experimentService = inject(Experiment);
  private readonly deploymentService = inject(Deployment);
  private readonly jobService = inject(Jobs);
  private readonly notificationService = inject(Notification);
  private readonly dialog = inject(MatDialog);

  runId = signal('');
  projectId = signal<number | null>(null);
  jobId = signal<number | null>(null);
  job = signal<IJob | null>(null);
  runInfo = signal<IMLflowRun | null>(null);
  isDeploying = signal(false);
  showParams = signal(false);
  brokenImages = signal<Set<string>>(new Set());

  variant = computed(() => {
    const j = this.job();
    if (j?.model_variant) return j.model_variant;
    return this.runInfo()?.tags?.['model_family'] || '';
  });
  isDetection = computed(() => isDetectionModel(this.variant()));
  isImported = computed(() => this.runInfo()?.tags?.['source'] === 'imported');
  tags = computed(() => this.runInfo()?.tags || {});
  testMissing = computed(() => this.tags()['test_split'] === 'missing');

  modelSha = computed(() => (this.runInfo()?.params?.['model_sha256'] || '').substring(0, 12));

  valTiles = computed(() => this.tilesFor('best_val/'));
  testTiles = computed(() => this.tilesFor('test/'));

  paramsList = computed(() =>
    Object.entries(this.runInfo()?.params || {}).sort(([a], [b]) => a.localeCompare(b)));

  /** 차트 부품이 알려 주는 run 상태 (학습 중 여부) */
  liveStatus = signal<string | null>(null);
  isLive = computed(() => (this.liveStatus() ?? this.runInfo()?.status) === 'RUNNING');

  /** 선택된 체크포인트의 최종 검증 그림: 데이터마다 P-R 곡선과 Confusion Matrix 를 나란히 (없는 그림은 숨김) */
  evalPlots = computed(() => this.isDetection() && !this.isImported() && !this.isLive() ? [
    { path: 'training/eval_val/BoxPR_curve.png', label: 'P-R 곡선 · Validation' },
    { path: 'training/eval_val/confusion_matrix.png', label: 'Confusion Matrix · Validation' },
    { path: 'training/eval_test/BoxPR_curve.png', label: 'P-R 곡선 · Test' },
    { path: 'training/eval_test/confusion_matrix.png', label: 'Confusion Matrix · Test' },
  ].filter(p => !this.brokenImages().has(p.path)) : []);

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('runId')!;
    const q = this.route.snapshot.queryParamMap;
    this.runId.set(id);
    if (q.get('projectId')) this.projectId.set(+q.get('projectId')!);
    if (q.get('jobId')) {
      this.jobId.set(+q.get('jobId')!);
      this.jobService.getJob(+q.get('jobId')!).subscribe({ next: j => this.job.set(j), error: () => { } });
    }
    this.experimentService.getRunDetail(id).subscribe({
      next: info => this.runInfo.set(info),
      error: () => this.notificationService.showError('상세 정보를 불러오지 못했습니다.'),
    });
  }

  /** 학습이 끝나면 최종 지표(best_val, test)와 상태를 다시 받음 */
  onRunStatus(status: string) {
    const wasLive = this.isLive();
    this.liveStatus.set(status);
    if (wasLive && status !== 'RUNNING') {
      this.experimentService.getRunDetail(this.runId()).subscribe({ next: info => this.runInfo.set(info) });
      if (this.jobId()) this.jobService.getJob(this.jobId()!).subscribe({ next: j => this.job.set(j) });
    }
  }

  openMlflow() {
    const exp = this.job()?.experiment_id ?? this.route.snapshot.queryParamMap.get('expId');
    window.open(`${this.experimentService.mlflowUiUrl}/#/experiments/${exp}/runs/${this.runId()}`, '_blank');
  }

  private tilesFor(prefix: string): MetricTile[] {
    const m = this.runInfo()?.metrics || {};
    return Object.entries(m).filter(([k]) => k.startsWith(prefix)).map(([k, v]) => {
      const name = k.substring(prefix.length);
      return { key: k, label: METRIC_LABELS[name] || name, value: v };
    }).sort((a, b) => a.key.localeCompare(b.key));
  }

  formatMetric(v: number): string {
    return v >= 0 && v <= 1 ? `${(v * 100).toFixed(2)}%` : v.toFixed(4);
  }

  previewUrl(path: string) {
    return this.experimentService.getArtifactPreviewUrl(this.runId(), path);
  }

  /** 최종 검증 그림을 모달로 크게 보기 (이전/다음으로 다른 그림도 넘겨 봄) */
  openPlot(index: number) {
    const job = this.jobId() ? `job${this.jobId()}_` : '';
    const data: ImageViewerData = {
      index,
      images: this.evalPlots().map(p => ({
        src: this.previewUrl(p.path),
        title: p.label,
        fileName: `${job}${p.path.split('/').slice(-2).join('_')}`,
      })),
    };
    this.dialog.open(ImageViewerDialog, {
      data, width: '1400px', maxWidth: '96vw', height: '92vh', panelClass: 'image-viewer-panel', autoFocus: false,
    });
  }

  onImgError(path: string) {
    this.brokenImages.update(s => new Set(s).add(path));
  }

  onDeployModel() {
    if (!this.runInfo()) return;
    if (!confirm(`이 모델(Run ${this.runId().substring(0, 8)})으로 추론 서버를 실행할까요? MLOps PC에서 확인용으로만 쓰이며 운영 PC에는 반영되지 않습니다.`)) return;
    this.isDeploying.set(true);
    this.deploymentService.createDeployment({
      project_id: this.projectId() ?? this.job()?.project_id ?? 1,
      model_name: this.tags()['model_variant'] || this.variant(),
      run_id: this.runId(),
      job_id: this.jobId() ?? undefined,
    }).subscribe({
      next: () => {
        this.isDeploying.set(false);
        this.notificationService.showSuccess('추론 서버를 시작했습니다. 추론 테스트 메뉴에서 확인하세요.');
        this.router.navigate(['/dashboard/deployments']);
      },
      error: (err: Error) => {
        this.isDeploying.set(false);
        this.notificationService.showWarning(err.message || '추론 서버 실행 요청에 실패했습니다.');
      },
    });
  }

  goEvaluation() {
    this.router.navigate(['/dashboard/evaluations'], {
      queryParams: { projectId: this.projectId() ?? this.job()?.project_id },
    });
  }

  goBack() {
    this.router.navigate(['/dashboard/models'], {
      queryParams: { projectId: this.projectId(), variant: this.variant() || null },
    });
  }

  getRelativeTime(ts?: number | string | null): string {
    if (!ts) return '-';
    const d = new Date(ts);
    return isNaN(d.getTime()) ? '-' : formatDistanceToNow(d, { addSuffix: true, locale: ko });
  }
}
