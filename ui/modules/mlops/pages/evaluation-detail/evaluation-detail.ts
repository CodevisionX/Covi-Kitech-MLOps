import { Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';
import { EvaluationApi } from '../../services/apis/evaluation';
import { DatasetApi } from '../../services/apis/dataset';
import { Jobs } from '../../services/apis/job';
import { Notification } from '../../services/notification';
import { IEvaluation, IEvaluationRow } from '../../services/apis/models/evaluation.model';
import { IJob } from '../../services/apis/models/job.model';
import { IDatasetVersion } from '../../services/apis/models/dataset.model';
import { parseCsv } from './csv';
import { MatDialog } from '@angular/material/dialog';
import { SlotViewDialog, SlotViewData } from '../../components/dialogs/slot-view/slot-view';

const TERMINAL = ['FINISHED', 'FAILED'];
const PAGE_SIZE = 100;

type ResultFilter = 'all' | 'wrong' | 'panel_not_6' | 'correct';

interface AccRow { key: string; correct?: number; total?: number; accuracy: number; }

@Component({
  selector: 'app-evaluation-detail',
  standalone: false,
  templateUrl: './evaluation-detail.html',
  styleUrl: './evaluation-detail.scss',
})
export class EvaluationDetail implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  protected readonly api = inject(EvaluationApi);
  private readonly datasetApi = inject(DatasetApi);
  private readonly jobs = inject(Jobs);
  private readonly notification = inject(Notification);
  private readonly dialog = inject(MatDialog);

  id = 0;
  evaluation = signal<IEvaluation | null>(null);
  detJob = signal<IJob | null>(null);
  recJob = signal<IJob | null>(null);
  dataset = signal<IDatasetVersion | null>(null);
  rows = signal<IEvaluationRow[]>([]);
  csvLoading = signal(false);
  filter = signal<ResultFilter>('all');
  page = signal(0);
  logs = signal<string | null>(null);
  showLogs = signal(false);

  readonly filters: { key: ResultFilter; label: string }[] = [
    { key: 'all', label: '전체' },
    { key: 'wrong', label: '틀림' },
    { key: 'panel_not_6', label: '박스 6개 아님' },
    { key: 'correct', label: '정답' },
  ];
  readonly columns = ['image', 'panel', 'slot', 'gt', 'pred', 'result', 'rec_score', 'det_conf'];

  isFinished = computed(() => this.evaluation()?.status === 'FINISHED');
  m = computed(() => this.evaluation()?.metrics || {});

  tiles = computed(() => {
    const m = this.m();
    return [
      { label: '슬롯 정확도', value: this.pct(m['e2e/slot_accuracy']), main: true,
        help: '정답이 있는 슬롯 중 인식 결과가 정확히 맞은 비율' },
      { label: '정규화 편집거리', value: this.num(m['e2e/norm_edit_dis']),
        help: '1에 가까울수록 틀린 글자 수가 적음' },
      { label: '6개 검출 패널', value: this.pct(m['e2e/panel_detect6_rate']),
        help: '박스가 정확히 6개 검출된 패널 비율 (6개가 아니면 운영 코드는 그 패널을 건너뜀)' },
      { label: '검출된 패널의 슬롯 정확도', value: this.pct(m['e2e/slot_accuracy_on_detected']),
        help: '6개 검출된 패널만 놓고 본 인식 정확도' },
      { label: '패널 전체 정답', value: this.pct(m['e2e/panel_all_correct_rate']),
        help: '모든 슬롯이 맞은 패널 비율' },
      { label: '이미지 전체 정답', value: this.pct(m['e2e/image_all_correct_rate']),
        help: '모든 패널의 모든 슬롯이 맞은 이미지 비율' },
      { label: '채점 슬롯 / 패널', value: `${m['e2e/labeled_slots'] ?? '-'} / ${m['e2e/panels'] ?? '-'}`,
        help: '정답이 있는 슬롯 수 / 평가한 패널 수' },
    ];
  });

  perSlot = computed<AccRow[]>(() => this.accRows('per_slot', k => `슬롯 ${k}`,
    () => Object.entries(this.m()).filter(([k]) => /^e2e\/slot\d+_accuracy$/.test(k))
      .map(([k, v]) => ({ key: `슬롯 ${k.match(/slot(\d+)/)![1]}`, accuracy: v }))));

  perPanel = computed<AccRow[]>(() => this.accRows('per_panel', k => k,
    () => Object.entries(this.m()).filter(([k]) => k.startsWith('e2e/panel/'))
      .map(([k, v]) => ({ key: k.slice('e2e/panel/'.length).replace(/_accuracy$/, ''), accuracy: v }))));

  counts = computed(() => {
    const c: Record<string, number> = { all: this.rows().length };
    for (const r of this.rows()) c[r.result] = (c[r.result] || 0) + 1;
    return c;
  });

  filtered = computed(() => {
    const f = this.filter();
    return f === 'all' ? this.rows() : this.rows().filter(r => r.result === f);
  });
  pageCount = computed(() => Math.max(1, Math.ceil(this.filtered().length / PAGE_SIZE)));
  pageRows = computed(() => this.filtered().slice(this.page() * PAGE_SIZE, (this.page() + 1) * PAGE_SIZE));

  private timer: any = null;

  ngOnInit() {
    this.id = +this.route.snapshot.paramMap.get('evaluationId')!;
    this.load(true);
  }

  ngOnDestroy() {
    this.stopPolling();
  }

  load(first = false) {
    this.api.get(this.id).subscribe({
      next: ev => {
        const wasFinished = this.isFinished();
        this.evaluation.set(ev);
        if (first) this.loadRelated(ev);
        if (TERMINAL.includes(ev.status)) {
          this.stopPolling();
          if (ev.status === 'FINISHED' && (!wasFinished || first)) this.loadCsv();
          if (this.showLogs()) this.loadLogs();
        } else if (!this.timer) {
          this.timer = setInterval(() => this.load(), 3000);
        }
      },
      error: e => {
        this.stopPolling();
        this.notification.showError(e.message);
      },
    });
  }

  private stopPolling() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  private loadRelated(ev: IEvaluation) {
    this.jobs.getJob(ev.detection_job_id).subscribe({ next: j => this.detJob.set(j), error: () => {} });
    this.jobs.getJob(ev.recognition_job_id).subscribe({ next: j => this.recJob.set(j), error: () => {} });
    this.datasetApi.getVersion(ev.dataset_version_id).subscribe({ next: v => this.dataset.set(v), error: () => {} });
  }

  loadCsv() {
    this.csvLoading.set(true);
    this.api.getPredictionsCsv(this.id).subscribe({
      next: text => {
        this.rows.set(parseCsv(text) as unknown as IEvaluationRow[]);
        this.csvLoading.set(false);
      },
      error: e => {
        this.csvLoading.set(false);
        this.notification.showError(`결과 CSV를 불러오지 못했습니다: ${e.message}`);
      },
    });
  }

  /** 백엔드가 text/plain 으로 주므로 파일 이름을 붙여 브라우저에서 저장 (BOM 유지: 엑셀 한글) */
  downloadCsv() {
    this.api.getPredictionsCsv(this.id).subscribe({
      next: text => {
        const body = text.charCodeAt(0) === 0xfeff ? text : '\ufeff' + text;
        const url = URL.createObjectURL(new Blob([body], { type: 'text/csv;charset=utf-8' }));
        const a = document.createElement('a');
        a.href = url;
        a.download = `e2e_eval${this.id}_predictions.csv`;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: e => this.notification.showError(e.message),
    });
  }

  toggleLogs() {
    this.showLogs.set(!this.showLogs());
    if (this.showLogs()) this.loadLogs();
  }

  loadLogs() {
    this.api.getLogs(this.id).subscribe({
      next: t => this.logs.set(t || '(로그 없음)'),
      error: e => this.logs.set(`로그를 불러오지 못했습니다: ${e.message}`),
    });
  }

  setFilter(f: ResultFilter) {
    this.filter.set(f);
    this.page.set(0);
  }

  prevPage() { this.page.set(Math.max(0, this.page() - 1)); }
  nextPage() { this.page.set(Math.min(this.pageCount() - 1, this.page() + 1)); }

  remove() {
    const ev = this.evaluation();
    if (!ev) return;
    const running = !TERMINAL.includes(ev.status);
    if (!confirm(`평가 #${ev.id}를 삭제할까요?${running ? ' 실행 중인 평가는 중단됩니다.' : ''}`)) return;
    this.api.delete(ev.id).subscribe({
      next: () => {
        this.notification.showSuccess('삭제했습니다.');
        this.goBack();
      },
      error: e => this.notification.showError(e.message),
    });
  }

  goBack() {
    this.router.navigate(['/dashboard/evaluations']);
  }

  goModels(job: IJob | null) {
    const ev = this.evaluation();
    this.router.navigate(['/dashboard/models'], {
      queryParams: { projectId: ev?.project_id, variant: job?.model_variant },
    });
  }

  jobOrigin(job: IJob | null): string {
    if (!job) return '';
    if (job.tags?.['source'] === 'imported') return `업로드 모델${job.tags?.['import_name'] ? ' · ' + job.tags['import_name'] : ''}`;
    return job.tags?.['dataset_version'] ? `학습 데이터 ${job.tags['dataset_version']}` : '학습 모델';
  }

  /** 슬롯 행을 누르면 패널·슬롯 이미지를 띄웁니다. 현재 필터 목록 안에서 이전/다음으로 넘겨 볼 수 있습니다. */
  openSlot(row: IEvaluationRow) {
    const rows = this.filtered();
    const data: SlotViewData = { evaluationId: this.id, rows, index: Math.max(0, rows.indexOf(row)) };
    this.dialog.open(SlotViewDialog, { data, width: '1200px', maxWidth: '95vw', maxHeight: '95vh', autoFocus: false });
  }

  resultLabel(r: string): string {
    return ({ correct: '정답', wrong: '틀림', panel_not_6: '박스 6개 아님', unlabeled: '정답 없음' } as any)[r] || r;
  }

  private accRows(summaryKey: string, label: (k: string) => string, fallback: () => AccRow[]): AccRow[] {
    const s = this.evaluation()?.summary?.[summaryKey] as Record<string, any> | undefined;
    if (s && Object.keys(s).length) {
      return Object.entries(s).map(([k, v]) => ({ key: label(k), correct: v.correct, total: v.total, accuracy: v.accuracy }));
    }
    return fallback();
  }

  pct(v?: number | null): string {
    return v === undefined || v === null ? '-' : `${(v * 100).toFixed(1)}%`;
  }

  num(v?: number | null): string {
    return v === undefined || v === null ? '-' : v.toFixed(4);
  }

  relTime(d?: string | null): string {
    return d ? formatDistanceToNow(new Date(d), { addSuffix: true, locale: ko }) : '-';
  }
}
