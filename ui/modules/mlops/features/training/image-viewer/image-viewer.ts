import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { Notification } from '../../../services/notification';

export interface ViewerImage {
  src: string;
  title: string;
  /** 다운로드할 때 쓰는 파일 이름 */
  fileName: string;
}

export interface ImageViewerData {
  images: ViewerImage[];
  index: number;
}

const MIN_SCALE = 0.25;
const MAX_SCALE = 8;
const STEP = 1.25;

/** 그림 크게 보기: 확대·축소, 드래그 이동, 다운로드, 이전/다음 */
@Component({
  selector: 'app-image-viewer',
  standalone: false,
  templateUrl: './image-viewer.html',
  styleUrl: './image-viewer.scss',
})
export class ImageViewerDialog {
  private readonly data = inject<ImageViewerData>(MAT_DIALOG_DATA);
  readonly dialogRef = inject(MatDialogRef<ImageViewerDialog>);
  private readonly notification = inject(Notification);

  readonly images = this.data.images;
  index = signal(this.data.index);
  current = computed(() => this.images[this.index()]);

  /** 1 = 화면에 맞춤 (퍼센트는 맞춤 크기 기준) */
  scale = signal(1);
  x = signal(0);
  y = signal(0);
  downloading = signal(false);

  transform = computed(() => `translate(${this.x()}px, ${this.y()}px) scale(${this.scale()})`);
  percent = computed(() => Math.round(this.scale() * 100));

  private drag: { sx: number; sy: number; ox: number; oy: number } | null = null;
  dragging = signal(false);

  zoom(factor: number) {
    const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, this.scale() * factor));
    // 가운데를 기준으로 확대하므로 이동량도 같은 비율로 맞춤
    const r = next / this.scale();
    this.x.update(v => v * r);
    this.y.update(v => v * r);
    this.scale.set(next);
  }

  fit() {
    this.scale.set(1);
    this.x.set(0);
    this.y.set(0);
  }

  go(delta: number) {
    const n = this.index() + delta;
    if (n < 0 || n >= this.images.length) return;
    this.index.set(n);
    this.fit();
  }

  onWheel(e: WheelEvent) {
    e.preventDefault();
    this.zoom(e.deltaY < 0 ? STEP : 1 / STEP);
  }

  onPointerDown(e: PointerEvent) {
    if (e.button !== 0) return;
    this.drag = { sx: e.clientX, sy: e.clientY, ox: this.x(), oy: this.y() };
    this.dragging.set(true);
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  }

  onPointerMove(e: PointerEvent) {
    if (!this.drag) return;
    this.x.set(this.drag.ox + e.clientX - this.drag.sx);
    this.y.set(this.drag.oy + e.clientY - this.drag.sy);
  }

  onPointerUp() {
    this.drag = null;
    this.dragging.set(false);
  }

  /** 다른 주소(백엔드)의 파일은 a[download] 가 무시되므로 받아서 저장 */
  async download() {
    const img = this.current();
    this.downloading.set(true);
    try {
      const res = await fetch(img.src);
      if (!res.ok) throw new Error(`${res.status}`);
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement('a');
      a.href = url;
      a.download = img.fileName;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      this.notification.showError('그림을 내려받지 못했습니다.');
    } finally {
      this.downloading.set(false);
    }
  }

  @HostListener('document:keydown', ['$event'])
  onKey(e: KeyboardEvent) {
    if (e.key === '+' || e.key === '=') this.zoom(STEP);
    else if (e.key === '-') this.zoom(1 / STEP);
    else if (e.key === '0') this.fit();
    else if (e.key === 'ArrowLeft') this.go(-1);
    else if (e.key === 'ArrowRight') this.go(1);
  }
}
