import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { Chart, registerables, ChartConfiguration, ChartOptions } from 'chart.js';
import { Experiment } from '../../services/apis/experiment';
import { Notification } from '../../services/notification';
import { IMLflowRun } from '../../services/apis/models/experiment.model';
import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';

Chart.register(...registerables);

@Component({
  selector: 'app-model-detail',
  standalone: false,
  templateUrl: './model-detail.html',
  styleUrl: './model-detail.scss',
})
export class ModelDetail {

  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  protected readonly experimentService = inject(Experiment);
  private readonly notificationService = inject(Notification);

  // 상태 관리 Signals
  runId = signal<string>('');
  projectId = signal<number | null>(null);
  runInfo = signal<IMLflowRun | null>(null); // 상세 정보 추가
  metricsData = signal<any>(null);
  isDeploying = signal<boolean>(false);

  protected readonly groundTruthUrl = computed(() =>
    this.experimentService.getArtifactPreviewUrl(this.runId(), 'val_batch0_labels.jpg')
  );

  protected readonly predictionUrl = computed(() =>
    this.experimentService.getArtifactPreviewUrl(this.runId(), 'val_batch0_pred.jpg')
  );

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('runId')!;
    const pId = this.route.snapshot.queryParamMap.get('projectId');

    this.runId.set(id);
    if (pId) this.projectId.set(+pId);

    this.loadRunDetail(id);
    this.loadMetricsHistory(id);
  }

  loadRunDetail(runId: string) {
    this.experimentService.getRunDetail(runId).subscribe({
      next: (info) => this.runInfo.set(info),
      error: (err) => this.notificationService.showError('상세 정보를 불러오지 못했습니다.')
    });
  }

  loadMetricsHistory(runId: string) {
    this.experimentService.getMetricsHistory(runId).subscribe({
      next: (data) => this.metricsData.set(data),
      error: (err) => console.error('메트릭 로드 실패:', err)
    });
  }

  onDeployModel() {
    const info = this.runInfo();
    if (!info) return;

    if (confirm(`현재 모델(Run ID: ${this.runId().substring(0, 8)})을 BentoML로 배포하시겠습니까?`)) {
      this.isDeploying.set(true);

      // TODO: 배포 API 호출 (BentoML 패키징 트리거)
      setTimeout(() => {
        this.isDeploying.set(false);
        this.notificationService.showSuccess('🚀 배포 프로세스가 시작되었습니다. 배포 탭에서 확인하세요.');
        this.router.navigate(['/dashboard/deployments']);
      }, 2000);
    }
  }

  goBack() {
    this.router.navigate(['/dashboard/models'], {
      queryParams: { projectId: this.projectId() }
    });
  }

  onImgError(event: any) {
    const fallbackSrc = 'assets/no_image.png';

    if (event.target.src !== fallbackSrc) {
      event.target.src = fallbackSrc;
    }
  }

  mAPChartData = computed<ChartConfiguration<'line'>['data']>(() => {
    const data = this.metricsData();
    const key = 'metrics/mAP50B';
    if (!data || !data[key] || data[key].length === 0) {
      return { labels: [], datasets: [] };
    }

    return {
      labels: data[key].map((_: any, i: number) => `Epoch ${i + 1}`),
      datasets: [{
        data: data[key],
        label: 'mAP@0.5',
        borderColor: '#002387',
        backgroundColor: 'rgba(0, 35, 135, 0.1)',
        fill: true,
        tension: 0.4,
        pointRadius: 2
      }]
    };
  });

  lossChartData = computed<ChartConfiguration<'line'>['data']>(() => {
    const data = this.metricsData();
    const boxLoss = data?.['train/box_loss'] || [];
    const clsLoss = data?.['train/cls_loss'] || [];

    if (boxLoss.length === 0 && clsLoss.length === 0) {
      return { labels: [], datasets: [] };
    }

    return {
      labels: boxLoss.length > 0
        ? boxLoss.map((_: any, i: number) => `Epoch ${i + 1}`)
        : clsLoss.map((_: any, i: number) => `Epoch ${i + 1}`),
      datasets: [
        { data: boxLoss, label: 'Box Loss', borderColor: '#E91E63', tension: 0.4, fill: false },
        { data: clsLoss, label: 'Class Loss', borderColor: '#4CAF50', tension: 0.4, fill: false }
      ]
    };
  });

  chartOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'top' },
      tooltip: { mode: 'index', intersect: false }
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: {
          // 소수점이 매우 길 경우를 대비해 포맷팅
          callback: function (value) {
            return Number(value).toFixed(4);
          }
        }
      },
      x: {
        grid: { display: false }
      }
    }
  };

  getRelativeTime(timestamp?: number | string | null): string {
    if (!timestamp) return '-';

    try {
      // 숫자인 경우(MLflow 타임스탬프)와 문자열인 경우 모두 처리
      const date = typeof timestamp === 'number' ? new Date(timestamp) : new Date(timestamp);

      // 유효하지 않은 날짜 체크
      if (isNaN(date.getTime())) return '-';

      return formatDistanceToNow(date, { addSuffix: true, locale: ko });
    } catch (error) {
      return '-';
    }
  }

}
