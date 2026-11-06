import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { Deployment } from '../../services/apis/deployment';
import { Jobs } from '../../services/apis/job';
import { IDeployment } from '../../services/apis/models/deployment.model';
import { IJob } from '../../services/apis/models/job.model';
import { Notification } from '../../services/notification';
import { Box, PANEL_SLOTS, sortBoxes2x3 } from './slot-order';
import { isDetectionModel, modelTask } from '../../configs/model-config';
import { parseNpy } from './npy';

interface DetResult {
  file: File;
  boxes: Box[];
  slots: Box[] | null;        // 정확히 6개일 때만 슬롯 순서
  rendered: string;           // 박스를 그린 이미지 (data URL)
  width: number;
  height: number;
  latencyMs: number;
  raw: any;
  error?: string;
}

interface RecResult {
  file: File;
  thumb: string;
  text: string;
  score: number;
  gt?: string;
  error?: string;
}

const REC_BATCH = 32;

/** YOLO26 / PP-OCRv6 서빙 컨테이너를 직접 호출해 확인하는 화면 */
@Component({
  selector: 'app-model-validation-pyfunc',
  standalone: false,
  templateUrl: './model-validation-pyfunc.html',
  styleUrl: './model-validation-pyfunc.scss',
})
export class ModelValidationPyfunc implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly deploymentService = inject(Deployment);
  private readonly jobService = inject(Jobs);
  private readonly notificationService = inject(Notification);

  deployment = signal<IDeployment | null>(null);
  job = signal<IJob | null>(null);
  family = computed(() => this.deployment()?.model_family || this.job()?.model_variant || '');
  isDetection = computed(() => isDetectionModel(this.family()));
  isTimeseries = computed(() => modelTask(this.family()) === 'timeseries');

  // 시계열: X.npy 를 올려 예측, y.npy 가 있으면 채점
  tsXFile = signal<File | null>(null);
  tsYFile = signal<File | null>(null);
  tsXName = computed(() => this.tsXFile()?.name || '');
  tsYName = computed(() => this.tsYFile()?.name || '');
  tsResult = signal<{
    rows: { pred: string; gt?: string; prob?: string; wrong?: boolean }[];
    classification: boolean; hasGt: boolean; latencyMs: number;
    metric?: { label: string; value: string };
  } | null>(null);

  files = signal<File[]>([]);
  isRunning = signal(false);
  progress = signal(0);

  // 검출 설정 (기본값은 현장 운영 코드와 같음)
  detParams = { conf: 0.25, iou: 0.3, max_det: 20, imgsz: 640 };
  detResults = signal<DetResult[]>([]);
  showRaw = signal<number | null>(null);
  readonly PANEL_SLOTS = PANEL_SLOTS;

  // 인식
  recResults = signal<RecResult[]>([]);
  labels = signal<Map<string, string>>(new Map());
  labelsFileName = signal('');
  recLatencyMs = signal(0);
  showOnlyWrong = signal(false);

  recSummary = computed(() => {
    const labeled = this.recResults().filter(r => r.gt !== undefined && !r.error);
    const correct = labeled.filter(r => r.text === r.gt).length;
    return { labeled: labeled.length, correct, acc: labeled.length ? correct / labeled.length : null };
  });
  visibleRecResults = computed(() => this.showOnlyWrong()
    ? this.recResults().filter(r => r.gt !== undefined && r.text !== r.gt) : this.recResults());

  detSummary = computed(() => {
    const ok = this.detResults().filter(r => !r.error);
    return { total: ok.length, six: ok.filter(r => r.boxes.length === PANEL_SLOTS).length };
  });

  ngOnInit() {
    const id = Number(this.route.snapshot.paramMap.get('deploymentId'));
    this.deploymentService.getDeploymentById(id).subscribe({
      next: dep => {
        this.deployment.set(dep);
        if (dep.job_id) this.jobService.getJob(dep.job_id).subscribe({ next: j => this.job.set(j), error: () => { } });
      },
      error: () => this.notificationService.showError('배포 정보를 불러오지 못했습니다.'),
    });
  }

  goBack() {
    this.router.navigate(['/dashboard/deployments']);
  }

  // ---------------------------------------------------------------- 파일 선택
  onFilesSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    this.setFiles(Array.from(input.files || []));
    input.value = '';
  }

  onDrop(event: DragEvent) {
    event.preventDefault();
    this.setFiles(Array.from(event.dataTransfer?.files || []));
  }

  private setFiles(list: File[]) {
    const images = list.filter(f => f.type.startsWith('image/') || /\.(png|jpe?g|bmp|webp)$/i.test(f.name))
      .sort((a, b) => a.name.localeCompare(b.name));
    if (!images.length) {
      this.notificationService.showWarning('이미지 파일을 선택해 주세요.');
      return;
    }
    this.files.set(images);
    this.detResults.set([]);
    this.recResults.set([]);
  }

  clear() {
    this.files.set([]);
    this.detResults.set([]);
    this.recResults.set([]);
  }

  /** "상대경로\t정답" 형식 (test_list.txt 등). 파일 이름으로 맞춥니다. */
  async onLabelsSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    const text = (await file.text()).replace(/^﻿/, '');
    const map = new Map<string, string>();
    for (const line of text.split(/\r?\n/)) {
      if (!line.trim()) continue;
      const tab = line.indexOf('\t');
      if (tab < 0) continue;
      const name = line.substring(0, tab).split(/[\\/]/).pop()!;
      map.set(name, line.substring(tab + 1).trim());
    }
    this.labels.set(map);
    this.labelsFileName.set(`${file.name} (${map.size}줄)`);
    this.recResults.update(rs => rs.map(r => ({ ...r, gt: map.get(r.file.name) })));
  }

  run() {
    if (this.isDetection()) this.runDetection(); else this.runRecognition();
  }

  // ---------------------------------------------------------------- 검출
  private async runDetection() {
    const dep = this.deployment();
    if (!dep || !this.files().length) return;
    this.isRunning.set(true);
    this.detResults.set([]);
    const params = {
      conf: Number(this.detParams.conf), iou: Number(this.detParams.iou),
      max_det: Math.round(Number(this.detParams.max_det)), imgsz: Math.round(Number(this.detParams.imgsz)),
    };
    const files = this.files();
    for (let i = 0; i < files.length; i++) {
      this.progress.set(Math.round((i / files.length) * 100));
      const file = files[i];
      const t0 = performance.now();
      try {
        const res = await new Promise<any>((resolve, reject) =>
          this.deploymentService.predictImageFile(dep.id, file, params).subscribe({ next: resolve, error: reject }));
        const latencyMs = performance.now() - t0;
        const boxes: Box[] = res?.prediction?.boxes || [];
        const slots = boxes.length === PANEL_SLOTS ? sortBoxes2x3(boxes) : null;
        const drawn = await this.drawBoxes(file, boxes, slots);
        this.detResults.update(r => [...r, { file, boxes, slots, latencyMs, raw: res, ...drawn }]);
      } catch (e: any) {
        this.detResults.update(r => [...r, {
          file, boxes: [], slots: null, rendered: '', width: 0, height: 0,
          latencyMs: performance.now() - t0, raw: null, error: e?.message || String(e),
        }]);
      }
    }
    this.progress.set(100);
    this.isRunning.set(false);
  }

  private async drawBoxes(file: File, boxes: Box[], slots: Box[] | null) {
    const img = await this.loadImage(file);
    // 작은 패널 이미지는 화면에서 크게 늘어나므로 캔버스를 키워 그려 라벨이 숫자를 가리지 않게 합니다
    const k = Math.max(1, 1200 / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(img.naturalWidth * k);
    canvas.height = Math.round(img.naturalHeight * k);
    const ctx = canvas.getContext('2d')!;
    ctx.imageSmoothingEnabled = k < 2;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const scale = Math.max(1, Math.max(canvas.width, canvas.height) / 1200);
    const color = slots ? '#16a34a' : '#ea580c';
    ctx.lineWidth = 3 * scale;
    ctx.font = `bold ${Math.round(24 * scale)}px sans-serif`;
    for (const b of boxes) {
      const [x1, y1, x2, y2] = [b[0] * k, b[1] * k, b[2] * k, b[3] * k];
      ctx.strokeStyle = color;
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      // 신뢰도는 아래 표에 있으므로 그림에는 슬롯 번호만 (6개가 아니면 신뢰도)
      const slot = slots ? slots.indexOf(b) + 1 : 0;
      const label = slot ? `${slot}` : b[4].toFixed(2);
      const tw = ctx.measureText(label).width + 6 * scale;
      const th = 30 * scale;
      const ty = y1 - th >= 0 ? y1 - th : y2;
      ctx.fillStyle = color;
      ctx.fillRect(x1, ty, tw, th);
      ctx.fillStyle = '#fff';
      ctx.fillText(label, x1 + 3 * scale, ty + th - 7 * scale);
    }
    URL.revokeObjectURL(img.src);
    return { rendered: canvas.toDataURL('image/png'), width: img.naturalWidth, height: img.naturalHeight };
  }

  private loadImage(file: File): Promise<HTMLImageElement> {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error(`이미지를 열 수 없습니다: ${file.name}`));
      img.src = URL.createObjectURL(file);
    });
  }

  toggleRaw(i: number) {
    this.showRaw.set(this.showRaw() === i ? null : i);
  }

  // ---------------------------------------------------------------- 인식
  private async runRecognition() {
    const dep = this.deployment();
    const files = this.files();
    if (!dep || !files.length) return;
    this.isRunning.set(true);
    this.recResults.set([]);
    this.progress.set(0);
    const labels = this.labels();
    const t0 = performance.now();
    for (let i = 0; i < files.length; i += REC_BATCH) {
      const batch = files.slice(i, i + REC_BATCH);
      const dataUrls = await Promise.all(batch.map(f => this.readDataUrl(f)));
      const b64 = dataUrls.map(u => u.substring(u.indexOf(',') + 1));
      try {
        const res = await new Promise<any>((resolve, reject) =>
          this.deploymentService.predictImages(dep.id, b64).subscribe({ next: resolve, error: reject }));
        const preds: any[] = res?.prediction || [];
        this.recResults.update(r => [...r, ...batch.map((file, k) => ({
          file, thumb: dataUrls[k], text: preds[k]?.text ?? '', score: preds[k]?.score ?? 0,
          gt: labels.get(file.name),
        }))]);
      } catch (e: any) {
        this.recResults.update(r => [...r, ...batch.map((file, k) => ({
          file, thumb: dataUrls[k], text: '', score: 0, gt: labels.get(file.name),
          error: e?.message || String(e),
        }))]);
      }
      this.progress.set(Math.round(Math.min(1, (i + REC_BATCH) / files.length) * 100));
    }
    this.recLatencyMs.set(performance.now() - t0);
    this.isRunning.set(false);
  }

  private readDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result as string);
      r.onerror = () => reject(r.error);
      r.readAsDataURL(file);
    });
  }

  // ---------------------------------------------------------------- 시계열
  onTsFile(event: Event, kind: 'x' | 'y') {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] || null;
    input.value = '';
    (kind === 'x' ? this.tsXFile : this.tsYFile).set(file);
    this.tsResult.set(null);
  }

  async runTimeseries() {
    const dep = this.deployment();
    const x = this.tsXFile();
    if (!dep || !x) return;
    this.isRunning.set(true);
    const t0 = performance.now();
    try {
      const res = await new Promise<any>((resolve, reject) =>
        this.deploymentService.predictNpyFile(dep.id, x).subscribe({ next: resolve, error: reject }));
      const latencyMs = performance.now() - t0;
      const p = res?.prediction || {};
      const classification = Array.isArray(p.labels);
      const preds: any[] = classification ? p.labels : (p.values || []);
      let gt: number[][] | null = null;
      const yFile = this.tsYFile();
      if (yFile) {
        const y = parseNpy(await yFile.arrayBuffer());
        const width = y.shape.length > 1 ? y.shape[1] : 1;
        gt = Array.from({ length: y.shape[0] }, (_, i) => Array.from(y.data.slice(i * width, (i + 1) * width)));
        if (gt.length !== preds.length) {
          this.notificationService.showWarning(`정답 개수(${gt.length})가 예측 개수(${preds.length})와 달라 채점하지 않습니다.`);
          gt = null;
        }
      }
      const fmt = (v: number) => (Number.isInteger(v) ? `${v}` : v.toFixed(4));
      const rows = preds.map((v: any, i: number) => {
        const pred = classification ? `${v}${p.names?.[i] && p.names[i] !== `${v}` ? ` (${p.names[i]})` : ''}` : (v as number[]).map(fmt).join(', ');
        const g = gt ? gt[i] : undefined;
        return {
          pred,
          gt: g ? g.map(fmt).join(', ') : undefined,
          prob: classification ? `${Math.max(...p.probs[i]).toFixed(3)}` : undefined,
          wrong: classification && g ? g[0] !== v : false,
        };
      });
      let metric: { label: string; value: string } | undefined;
      if (gt && classification) {
        const correct = preds.filter((v: number, i: number) => gt![i][0] === v).length;
        metric = { label: '정확도', value: `${((correct / preds.length) * 100).toFixed(2)}% (${correct}/${preds.length})` };
      } else if (gt) {
        const errs = preds.flatMap((v: number[], i: number) => v.map((x, j) => Math.abs(x - gt![i][j])));
        metric = { label: 'MAE', value: (errs.reduce((a: number, b: number) => a + b, 0) / errs.length).toFixed(4) };
      }
      this.tsResult.set({ rows, classification, hasGt: !!gt, latencyMs, metric });
    } catch (e: any) {
      this.notificationService.showError(e?.message || String(e));
    } finally {
      this.isRunning.set(false);
    }
  }

  resultClass(r: RecResult): string {
    if (r.error) return 'error';
    if (r.gt === undefined) return '';
    return r.text === r.gt ? 'correct' : 'wrong';
  }
}
