import { Component, input, output } from '@angular/core';
import { ChartData, ChartOptions } from 'chart.js';
import { IMLflowRun } from '../../services/apis/models/experiment.model';

export interface RunDetailImage {
  tag: string;
  tagClass: 'label' | 'pred';
  url: string;
  alt: string;
}

/** YOLO·CNN 결과 상세의 공통 화면. 지표 계산과 배포 요청은 각 라우트 컴포넌트가 맡는다. */
@Component({
  selector: 'app-run-detail-view',
  standalone: false,
  templateUrl: './run-detail-view.html',
  styleUrl: './run-detail-view.scss',
})
export class RunDetailView {
  runId = input.required<string>();
  runInfo = input.required<IMLflowRun | null>();
  projectId = input.required<number | null>();
  startedAt = input.required<string>();
  isDeploying = input.required<boolean>();
  variantFallback = input.required<string>();
  chartOptions = input.required<ChartOptions<'line'>>();
  lossTitle = input.required<string>();
  lossChart = input.required<ChartData<'line'>>();
  /** 없으면 성능 차트 카드를 그리지 않는다 */
  performanceTitle = input<string>();
  performanceChart = input<ChartData<'line'>>();
  imagesTitle = input.required<string>();
  images = input.required<RunDetailImage[]>();

  back = output<void>();
  deploy = output<void>();
  imageError = output<Event>();
}
