import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { ChartConfiguration, ChartOptions } from 'chart.js';
import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';
import { Experiment } from '../../services/apis/experiment';
import { Deployment } from '../../services/apis/deployment';
import { Jobs } from '../../services/apis/job';
import { IMLflowRun } from '../../services/apis/models/experiment.model';
import { IJob } from '../../services/apis/models/job.model';
import { Notification } from '../../services/notification';

interface MetricTile { key: string; label: string; value: number; }
interface ChartGroup { title: string; data: ChartConfiguration<'line'>['data']; }

const METRIC_LABELS: Record<string, string> = {
  'mAP50': 'mAP@0.5',
  'mAP50-95': 'mAP@0.5:0.95',
  'precision': 'Precision',
  'recall': 'Recall',
  'acc': '정확도',
  'norm_edit_dis': '정규화 편집 유사도',
};

const COLORS = ['#002387', '#E91E63', '#4CAF50', '#FF9800', '#00ACC1', '#8E24AA'];

/** YOLO26 / PP-OCRv6 학습(또는 가져온 현장 모델) run 상세 */
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

  runId = signal('');
  projectId = signal<number | null>(null);
  jobId = signal<number | null>(null);
  job = signal<IJob | null>(null);
  runInfo = signal<IMLflowRun | null>(null);
  history = signal<Record<string, number[]>>({});
  isDeploying = signal(false);
  showParams = signal(false);
  brokenImages = signal<Set<string>>(new Set());

  variant = computed(() => {
    const j = this.job();
    if (j?.model_variant) return j.model_variant;
    const fam = this.runInfo()?.tags?.['model_family'] || '';
    return fam.startsWith('PP-OCR') ? 'PP-OCRv6' : fam.startsWith('YOLO26') ? 'YOLO26' : fam;
  });
  isDetection = computed(() => this.variant() === 'YOLO26');
  isImported = computed(() => this.runInfo()?.tags?.['source'] === 'imported');
  tags = computed(() => this.runInfo()?.tags || {});
  testMissing = computed(() => this.tags()['test_split'] === 'missing');

  modelSha = computed(() => (this.runInfo()?.params?.['model_sha256'] || '').substring(0, 12));

  valTiles = computed(() => this.tilesFor('best_val/'));
  testTiles = computed(() => this.tilesFor('test/'));

  paramsList = computed(() =>
    Object.entries(this.runInfo()?.params || {}).sort(([a], [b]) => a.localeCompare(b)));

  /** 기록된 지표 이름으로 차트를 묶습니다 (학습 손실 / 검증 손실 / 학습 지표 / 검증 지표) */
  chartGroups = computed<ChartGroup[]>(() => {
    const h = this.history();
    const keys = Object.keys(h).filter(k => h[k]?.length > 1
      && !k.startsWith('best_val/') && !k.startsWith('test/') && !k.startsWith('lr/')
      && k !== 'train/epoch' && k !== 'train/lr');
    const isLoss = (k: string) => /loss/i.test(k);
    const groups: [string, string[]][] = [
      ['학습 손실', keys.filter(k => k.startsWith('train/') && isLoss(k))],
      ['검증 손실', keys.filter(k => k.startsWith('val/') && isLoss(k))],
      ['학습 지표', keys.filter(k => k.startsWith('train/') && !isLoss(k))],
      ['검증 지표', keys.filter(k => (k.startsWith('val/') || k.startsWith('metrics/')) && !isLoss(k))],
    ];
    return groups.filter(([, ks]) => ks.length).map(([title, ks]) => {
      const len = Math.max(...ks.map(k => h[k].length));
      return {
        title,
        data: {
          labels: Array.from({ length: len }, (_, i) => `${i + 1}`),
          datasets: ks.map((k, i) => ({
            data: h[k], label: k.replace(/^(train|val|metrics)\//, '').replace(/_B$/, ''),
            borderColor: COLORS[i % COLORS.length], backgroundColor: COLORS[i % COLORS.length],
            tension: 0.3, fill: false, pointRadius: 2,
          })),
        },
      };
    });
  });

  /** YOLO 학습이 남기는 그림 (가져온 모델에는 없음) */
  plotImages = computed(() => this.isDetection() && !this.isImported() ? [
    { path: 'training/fit/val_batch0_labels.jpg', label: 'Validation 정답' },
    { path: 'training/fit/val_batch0_pred.jpg', label: 'Validation 예측' },
    { path: 'training/fit/results.png', label: '학습 곡선 (ultralytics)' },
    { path: 'training/fit/confusion_matrix.png', label: 'Confusion Matrix' },
  ].filter(p => !this.brokenImages().has(p.path)) : []);

  chartOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' }, tooltip: { mode: 'index', intersect: false } },
    scales: { x: { grid: { display: false }, title: { display: true, text: 'step / epoch' } } },
  };

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
    this.experimentService.getMetricsHistory(id).subscribe({
      next: data => this.history.set(data || {}),
      error: () => this.history.set({}),
    });
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

  onImgError(path: string) {
    this.brokenImages.update(s => new Set(s).add(path));
  }

  onDeployModel() {
    if (!this.runInfo()) return;
    if (!confirm(`이 모델(Run ${this.runId().substring(0, 8)})을 서빙 컨테이너로 배포하시겠습니까?`)) return;
    this.isDeploying.set(true);
    this.deploymentService.createDeployment({
      project_id: this.projectId() ?? this.job()?.project_id ?? 1,
      model_name: this.tags()['model_variant'] || this.variant(),
      run_id: this.runId(),
      job_id: this.jobId() ?? undefined,
    }).subscribe({
      next: () => {
        this.isDeploying.set(false);
        this.notificationService.showSuccess('배포를 시작했습니다.');
        this.router.navigate(['/dashboard/deployments']);
      },
      error: (err: Error) => {
        this.isDeploying.set(false);
        this.notificationService.showWarning(err.message || '배포 요청에 실패했습니다.');
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
