import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { Deployment } from '../../services/apis/deployment';
import { Jobs } from '../../services/apis/job';
import { IDeployment } from '../../services/apis/models/deployment.model';
import { IJob } from '../../services/apis/models/job.model';
import { Notification } from '../../services/notification';
import { Box, PANEL_SLOTS, sortBoxes2x3 } from './slot-order';

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
  isDetection = computed(() => this.family() === 'YOLO26');

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
    const canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(img, 0, 0);
    const scale = Math.max(1, Math.max(canvas.width, canvas.height) / 640);
    const color = slots ? '#16a34a' : '#ea580c';
    ctx.lineWidth = 2 * scale;
    ctx.font = `bold ${Math.round(12 * scale)}px sans-serif`;
    for (const b of boxes) {
      const [x1, y1, x2, y2, conf] = b;
      ctx.strokeStyle = color;
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      const slot = slots ? slots.indexOf(b) + 1 : 0;
      const label = slot ? `#${slot} ${conf.toFixed(2)}` : conf.toFixed(2);
      const tw = ctx.measureText(label).width + 6 * scale;
      const th = 16 * scale;
      const ty = y1 - th >= 0 ? y1 - th : y2;
      ctx.fillStyle = color;
      ctx.fillRect(x1, ty, tw, th);
      ctx.fillStyle = '#fff';
      ctx.fillText(label, x1 + 3 * scale, ty + th - 4 * scale);
    }
    URL.revokeObjectURL(img.src);
    return { rendered: canvas.toDataURL('image/png'), width: canvas.width, height: canvas.height };
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

  resultClass(r: RecResult): string {
    if (r.error) return 'error';
    if (r.gt === undefined) return '';
    return r.text === r.gt ? 'correct' : 'wrong';
  }
}
