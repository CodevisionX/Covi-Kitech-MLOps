import { Component, computed, effect, inject, input, OnDestroy, output, signal } from '@angular/core';
import { ChartConfiguration, ChartOptions } from 'chart.js';
import { Experiment } from '../../services/apis/experiment';

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
const LIVE_POLL_MS = 3000;

/**
 * 학습 run 의 추이 차트. 기록된 지표로 차트를 구성하므로 지표 이름·개수·검증 주기가 바뀌어도 그대로 동작합니다.
 *  - train/X 와 val/X 가 모두 있으면 한 차트에 겹침 (과적합 확인)
 *  - 나머지는 학습 손실 / 학습 지표 / 검증 손실 / 검증 성능으로 묶음
 *  - run 이 실행 중이면 주기적으로 갱신하고, 끝나면 statusChange 로 알림
 */
@Component({
  selector: 'app-training-charts',
  standalone: false,
  templateUrl: './training-charts.html',
  styleUrl: './training-charts.scss',
})
export class TrainingCharts implements OnDestroy {
  private readonly experiment = inject(Experiment);

  runId = input.required<string>();
  /** Precision/Recall 을 에폭별 선 대신 P-R 곡선으로 따로 보여 줄 때 차트에서 뺌 */
  hidePrecisionRecall = input(false);
  /** 차트 한 줄에 몇 개 */
  columns = input(2);
  chartHeight = input(280);
  statusChange = output<string>();

  series = signal<Record<string, [number, number][]>>({});
  params = signal<Record<string, string>>({});
  status = signal<string | null>(null);
  loaded = signal(false);
  isLive = computed(() => this.status() === 'RUNNING');
  private timer: ReturnType<typeof setInterval> | null = null;

  /** 차트에서 빼는 보조 기록 (학습률, 에폭 번호) */
  private static readonly SKIP = /^(lr\/|train\/(epoch|lr)$)/;
  /** 체크포인트 선택 기준으로 쓰는 지표 (있는 것 중 앞쪽 우선) */
  private static readonly BEST_KEYS = ['metrics/mAP50-95_B', 'val/mAP50-95', 'val/acc', 'val/norm_edit_dis'];

  constructor() {
    effect(() => {
      const id = this.runId();
      this.stop();
      this.series.set({});
      this.loaded.set(false);
      this.status.set(null);
      if (!id) return;
      this.load();
      this.timer = setInterval(() => {
        if (this.isLive() && !document.hidden) this.load();
      }, LIVE_POLL_MS);
    });
  }

  ngOnDestroy() {
    this.stop();
  }

  private stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  private load() {
    const id = this.runId();
    this.experiment.getMetricsSeries(id).subscribe({
      next: d => {
        if (id !== this.runId()) return;
        this.series.set(d.series || {});
        this.params.set(d.params || {});
        this.loaded.set(true);
        if (d.status !== this.status()) {
          this.status.set(d.status);
          this.statusChange.emit(d.status);
        }
      },
      error: () => this.loaded.set(true),
    });
  }

  /** x 축이 에폭인지 step 인지: 지표 이름이 아니라 기록 형태로 판단 (train/epoch 를 따로 남기면 step 기준) */
  stepAxis = computed(() => !!this.series()['train/epoch']?.length);

  /** 검증 주기: 학습 설정 우선, 없으면 실제 검증 기록 간격 중 최솟값 */
  evalInterval = computed(() => {
    const p = Number(this.params()['eval_batch_step']);
    if (p > 0) return p;
    const pts = Object.entries(this.series()).find(([k]) => k.startsWith('val/'))?.[1] || [];
    const gaps = pts.slice(1).map((v, i) => v[0] - pts[i][0]).filter(g => g > 0);
    return gaps.length ? Math.min(...gaps) : null;
  });

  bestPoint = computed(() => {
    const s = this.series();
    const key = TrainingCharts.BEST_KEYS.find(k => s[k]?.length)
      ?? Object.keys(s).find(k => (k.startsWith('val/') || k.startsWith('metrics/')) && !/loss/i.test(k) && s[k].length);
    if (!key) return null;
    // 에폭 축이면 학습 설정의 에폭 수까지만 후보로 봄.
    // (YOLO 는 학습이 끝난 뒤 선택된 모델을 한 번 더 검증해 '마지막 에폭 + 1' 로 기록함)
    const epochs = Number(this.params()['epochs']);
    const limit = !this.stepAxis() && epochs > 0 ? epochs : Infinity;
    const inTrain = s[key].filter(([x]) => x <= limit);
    const pts = inTrain.length ? inTrain : s[key];
    const best = pts.reduce((a, b) => (b[1] > a[1] ? b : a));
    return { key, label: `val ${this.shortName(key)}`, step: best[0], value: best[1], last: pts[pts.length - 1][0] };
  });

  /** 과적합 확인용 요약: 최고 지점 이후 진행량, val 손실이 최저점 대비 오르는지 */
  overfitNote = computed(() => {
    const b = this.bestPoint();
    if (!b) return '';
    const unit = this.stepAxis() ? 'step' : '에폭';
    const parts = [`최고 ${b.label} ${this.formatMetric(b.value)} @ ${unit} ${b.step}`];
    if (b.last > b.step) parts.push(`이후 ${b.last - b.step} ${unit} 동안 갱신 없음`);
    for (const [k, pts] of Object.entries(this.series())) {
      if (!k.startsWith('val/') || !/loss/i.test(k) || pts.length < 3) continue;
      const min = pts.reduce((a, c) => (c[1] < a[1] ? c : a));
      const last = pts[pts.length - 1];
      if (last[0] > min[0] && last[1] > min[1] * 1.05) {
        parts.push(`${k} 가 ${unit} ${min[0]} 이후 ${((last[1] / min[1] - 1) * 100).toFixed(0)}% 상승 (과적합 가능성)`);
      }
    }
    return parts.join(' · ');
  });

  chartGroups = computed<ChartGroup[]>(() => {
    const s = this.series();
    const keys = Object.keys(s).filter(k => s[k]?.length && !TrainingCharts.SKIP.test(k)
      && !(this.hidePrecisionRecall() && /precision|recall/i.test(k))).sort();
    const isLoss = (k: string) => /loss/i.test(k);
    const isVal = (k: string) => k.startsWith('val/') || k.startsWith('metrics/');
    const used = new Set<string>();
    const plans: { title: string; keys: string[]; pair?: boolean }[] = [];

    for (const k of keys.filter(k => k.startsWith('train/'))) {
      const v = 'val/' + k.slice('train/'.length);
      if (s[v]?.length) {
        plans.push({ title: `${this.shortName(k)} · train vs val`, keys: [k, v], pair: true });
        used.add(k); used.add(v);
      }
    }
    plans.sort((a, b) => Number(!isLoss(a.keys[0])) - Number(!isLoss(b.keys[0])));  // 손실 먼저
    const rest = keys.filter(k => !used.has(k));
    const groups: [string, string[]][] = [
      ['학습 손실', rest.filter(k => !isVal(k) && isLoss(k))],
      ['학습 지표', rest.filter(k => !isVal(k) && !isLoss(k))],
      ['검증 손실', rest.filter(k => isVal(k) && isLoss(k))],
      ['검증 성능', rest.filter(k => isVal(k) && !isLoss(k))],
    ];
    for (const [title, ks] of groups) if (ks.length) plans.push({ title, keys: ks });

    const best = this.bestPoint();
    return plans.map(p => {
      const datasets: any[] = p.keys.map((k, i) => ({
        data: s[k].map(([x, y]) => ({ x, y })),
        label: p.pair ? (k.startsWith('train/') ? 'train' : 'val') : this.shortName(k),
        borderColor: COLORS[i % COLORS.length], backgroundColor: COLORS[i % COLORS.length],
        borderWidth: 2, tension: 0.2, fill: false, pointRadius: s[k].length > 60 ? 0 : 2,
      }));
      if (best) {  // 최고 지점 세로선
        const ys = p.keys.flatMap(k => s[k].map(v => v[1]));
        datasets.push({
          data: [{ x: best.step, y: Math.min(...ys) }, { x: best.step, y: Math.max(...ys) }],
          label: `최고 (${best.step})`, borderColor: '#94a3b8', backgroundColor: '#94a3b8',
          borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, fill: false,
        });
      }
      return { title: p.title, data: { datasets } };
    });
  });

  chartOptions = computed<ChartOptions<'line'>>(() => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    parsing: false,
    plugins: { legend: { position: 'top' }, tooltip: { mode: 'nearest', intersect: false } },
    scales: {
      x: {
        type: 'linear', grid: { display: false },
        title: {
          display: true,
          text: this.stepAxis()
            ? `step${this.evalInterval() ? ` (검증: ${this.evalInterval()} step 마다)` : ''}`
            : 'epoch',
        },
      },
    },
  }));

  /** 'metrics/mAP50-95_B' -> 'mAP@0.5:0.95', 'train/box_loss' -> 'box_loss' */
  shortName(k: string): string {
    const name = k.replace(/^(train|val|metrics)\//, '').replace(/_B$/, '');
    return METRIC_LABELS[name] || name;
  }

  formatMetric(v: number): string {
    return v >= 0 && v <= 1 ? `${(v * 100).toFixed(2)}%` : v.toFixed(4);
  }
}
