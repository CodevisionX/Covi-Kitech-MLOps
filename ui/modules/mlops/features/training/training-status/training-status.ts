import { Component, computed, effect, ElementRef, inject, OnDestroy, OnInit, signal, ViewChild } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { Router } from '@angular/router';
import { Jobs } from '../../../services/apis/job';
import { Experiment } from '../../../services/apis/experiment';
import { IJob } from '../../../services/apis/models/job.model';
import { MODEL_CONFIGS, isDetectionModel } from '../../../configs/model-config';
import { TerminalService } from '../../../services/terminal';

const JOB_POLL_MS = 2000;

/** 실행 중인 학습의 현황: 진행도·소요 시간, 실시간 학습 추이 차트, 로그 */
@Component({
  selector: 'app-training-status-dialog',
  standalone: false,
  templateUrl: './training-status.html',
  styleUrl: './training-status.scss',
})
export class TrainingStatusDialog implements OnInit, OnDestroy {
  @ViewChild('logBox') private logBox?: ElementRef<HTMLElement>;

  private readonly jobs = inject(Jobs);
  private readonly experiment = inject(Experiment);
  private readonly router = inject(Router);
  private readonly dialogRef = inject(MatDialogRef<TrainingStatusDialog>);
  protected readonly terminal = inject(TerminalService);
  readonly data = inject<{ job: IJob }>(MAT_DIALOG_DATA);

  job = signal<IJob>(this.data.job);
  now = signal(Date.now());
  /** 0: 학습 추이, 1: 로그 */
  tab = signal(0);
  private timer: ReturnType<typeof setInterval> | null = null;

  hasCharts = computed(() => !!this.job().run_id && !!MODEL_CONFIGS[this.job().model_variant]?.pyfunc);
  isDetection = computed(() => isDetectionModel(this.job().model_variant));
  progress = computed(() => this.job().progress);
  percent = computed(() => {
    const p = this.progress();
    return p && p.total ? (p.epoch / p.total) * 100 : 0;
  });

  constructor() {
    // 새 로그가 오면 맨 아래 근처를 보고 있을 때만 따라 내려감
    effect(() => {
      if (!this.terminal.logs().length || !this.logBox) return;
      const el = this.logBox.nativeElement;
      if (el.scrollHeight - el.scrollTop - el.clientHeight < 120) {
        requestAnimationFrame(() => (el.scrollTop = el.scrollHeight));
      }
    });
  }

  ngOnInit() {
    this.terminal.startStreaming(this.job().id, this.job().status, 'job');
    this.timer = setInterval(() => {
      this.now.set(Date.now());
      if (document.hidden || !['RUNNING', 'PENDING'].includes(this.job().status)) return;
      this.jobs.getJob(this.job().id).subscribe({ next: j => this.job.set(j), error: () => { } });
    }, JOB_POLL_MS / 2);
  }

  ngOnDestroy() {
    if (this.timer) clearInterval(this.timer);
    this.terminal.close();
  }

  /** 로그 탭으로 오면 맨 아래(최신)로 */
  onTab(i: number) {
    this.tab.set(i);
    if (i === 1) setTimeout(() => {
      const el = this.logBox?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  /** 차트 쪽에서 run 이 끝났다고 알려 오면 작업 상태도 바로 갱신 */
  onRunStatus(status: string) {
    if (status !== 'RUNNING') this.jobs.getJob(this.job().id).subscribe({ next: j => this.job.set(j) });
  }

  elapsed(): string {
    const j = this.job();
    const from = j.started_at || j.created_at;
    if (!from || j.status === 'PENDING') return '-';
    const end = j.finished_at ? new Date(j.finished_at).getTime() : this.now();
    const sec = Math.max(0, Math.floor((end - new Date(from).getTime()) / 1000));
    const p = (n: number) => String(n).padStart(2, '0');
    return `${Math.floor(sec / 3600)}:${p(Math.floor(sec / 60) % 60)}:${p(sec % 60)}`;
  }

  startedAt(): string {
    const j = this.job();
    const v = j.started_at || j.created_at;
    if (!v) return '-';
    const d = new Date(v);
    const p = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }

  openMlflow() {
    const j = this.job();
    if (!j.run_id) return;
    window.open(`${this.experiment.mlflowUiUrl}/#/experiments/${j.experiment_id}/runs/${j.run_id}`, '_blank');
  }

  openDetail() {
    const j = this.job();
    if (!j.run_id) return;
    this.dialogRef.close();
    this.router.navigate(['/dashboard/models/run', 'v2', j.run_id],
      { queryParams: { projectId: j.project_id, expId: j.experiment_id, jobId: j.id } });
  }

  close() {
    this.dialogRef.close();
  }
}
