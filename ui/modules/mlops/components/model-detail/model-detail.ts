import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { Chart, registerables, ChartConfiguration, ChartOptions } from 'chart.js';
import { Experiment } from '../../services/apis/experiment';

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
  protected readonly experiment = inject(Experiment);

  // 상태 관리 Signals
  runId = signal<string>('');
  backExpId = signal<string | null>(null);
  metricsData = signal<any>(null);
  resultImages = signal<any[]>([]); // 추가적인 아티팩트 목록

  protected readonly groundTruthUrl = computed(() =>
    this.experiment.getArtifactPreviewUrl(this.runId(), 'val_batch0_labels.jpg')
  );

  protected readonly predictionUrl = computed(() =>
    this.experiment.getArtifactPreviewUrl(this.runId(), 'val_batch0_pred.jpg')
  );

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('runId')!;
    const expId = this.route.snapshot.queryParamMap.get('expId');

    this.runId.set(id);
    this.backExpId.set(expId);

    this.loadMetricsHistory(id);
  }

  loadMetricsHistory(runId: string) {
    this.experiment.getMetricsHistory(runId).subscribe({
      next: (data) => this.metricsData.set(data),
      error: (err) => console.error('메트릭 로드 실패:', err)
    });
  }

  goBack() {
    this.router.navigate(['/dashboard/models'], {
      queryParams: { expId: this.backExpId() }
    });
  }

  onImgError(event: any) {
    event.target.src = 'assets/images/no-image.png'; // 이미지 없을 시 대체
  }

  // --- 차트 설정 로직 (Deploy에서 가져옴) ---

  mAPChartData = computed<ChartConfiguration<'line'>['data']>(() => {
    const data = this.metricsData();
    if (!data || !data['metrics.mAP50(B)']) return { labels: [], datasets: [] };

    return {
      labels: data['metrics.mAP50(B)'].map((_: any, i: number) => `${i + 1} Epoch`),
      datasets: [
        {
          data: data['metrics.mAP50(B)'],
          label: 'mAP@0.5',
          borderColor: '#002387',
          backgroundColor: 'rgba(0, 35, 135, 0.1)',
          fill: true,
          tension: 0.4
        }
      ]
    };
  });

  lossChartData = computed<ChartConfiguration<'line'>['data']>(() => {
    const data = this.metricsData();
    if (!data || !data['train.box_loss']) return { labels: [], datasets: [] };

    return {
      labels: data['train.box_loss'].map((_: any, i: number) => `${i + 1} Epoch`),
      datasets: [
        {
          data: data['train.box_loss'],
          label: 'Box Loss',
          borderColor: '#E91E63',
          tension: 0.4
        },
        {
          data: data['train.cls_loss'] || [],
          label: 'Class Loss',
          borderColor: '#4CAF50',
          tension: 0.4
        }
      ]
    };
  });

  chartOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' } },
    scales: { y: { beginAtZero: true } }
  };

}
