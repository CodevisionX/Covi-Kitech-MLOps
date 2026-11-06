import { Component, inject, signal } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { Notification } from '../../../services/notification';
import { Jobs } from '../../../services/apis/job';
import { IJob } from '../../../services/apis/models/job.model';
import { isDetectionModel, modelsForTask } from '../../../configs/model-config';

const REC_FILES = ['inference.json', 'inference.pdiparams', 'inference.yml'];

@Component({
  selector: 'app-import-model-dialog',
  standalone: false,
  templateUrl: './import-model.html',
  styleUrl: './import-model.scss',
})
export class ImportModelDialog {
  private readonly jobs = inject(Jobs);
  private readonly dialogRef = inject(MatDialogRef<ImportModelDialog, IJob>);
  readonly data = inject<{ projectId: number; variant?: string; files?: File[] }>(MAT_DIALOG_DATA);
  private readonly notification = inject(Notification);

  /** 가져올 수 있는 모델: 검출·인식 (설정에서 만듦) */
  readonly variants = [
    ...modelsForTask('detection').map(name => ({ name, label: '검출' })),
    ...modelsForTask('recognition').map(name => ({ name, label: '인식' })),
  ];
  variant = this.variants.some(v => v.name === this.data.variant) ? this.data.variant! : this.variants[0].name;

  get isDetection(): boolean {
    return isDetectionModel(this.variant);
  }
  name = 'site-model';
  imgsz = 640;
  files = signal<File[]>([]);
  submitting = signal(false);
  error = signal<string | null>(null);

  readonly recFiles = REC_FILES;
  dragOver = signal(false);

  constructor() {
    // 학습 이력 화면의 버튼에 끌어다 놓은 파일로 열렸을 때
    if (this.data.files?.length) this.useFiles(this.data.files);
  }

  onVariantChange() {
    this.files.set([]);
    this.error.set(null);
  }

  onFiles(event: Event) {
    const input = event.target as HTMLInputElement;
    this.useFiles(Array.from(input.files ?? []));
    input.value = '';
  }

  onDragOver(e: DragEvent) {
    e.preventDefault();
    if (!this.submitting()) this.dragOver.set(true);
  }

  onDragLeave(e: DragEvent) {
    if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) this.dragOver.set(false);
  }

  async onDrop(e: DragEvent) {
    e.preventDefault();
    this.dragOver.set(false);
    if (this.submitting() || !e.dataTransfer) return;
    this.useFiles(await filesFromDrop(e.dataTransfer));
  }

  /** 받은 파일에서 모델 파일만 골라 쓰고, 종류(검출·인식)를 파일에 맞춥니다 */
  useFiles(all: File[]) {
    const pt = all.filter(f => f.name.toLowerCase().endsWith('.pt'));
    const rec = all.filter(f => REC_FILES.includes(f.name));
    const det = modelsForTask('detection');
    const recModels = modelsForTask('recognition');
    let picked = all;
    if (rec.length && (!pt.length || !this.isDetection)) {
      picked = rec;
      if (this.isDetection) this.switchVariant(recModels[0]);
    } else if (pt.length) {
      picked = pt;
      if (!this.isDetection) this.switchVariant(det[0]);
    }
    this.files.set(picked);
    this.error.set(this.problem());
  }

  private switchVariant(v: string) {
    this.variant = v;
    this.notification.showInfo(`파일에 맞춰 ${v} 모델로 바꿨습니다.`);
  }

  /** 올릴 파일 구성이 맞지 않으면 이유를 돌려줍니다 */
  problem(): string | null {
    const files = this.files();
    if (files.length === 0) return null;
    if (this.isDetection) {
      return files.length === 1 && files[0].name.toLowerCase().endsWith('.pt')
        ? null : '검출 모델은 .pt 파일 1개를 골라 주세요.';
    }
    const names = files.map(f => f.name).sort();
    return names.length === 3 && names.every((n, i) => n === [...REC_FILES].sort()[i])
      ? null : `인식 모델은 ${REC_FILES.join(', ')} 3개를 함께 골라 주세요.`;
  }

  get canSubmit(): boolean {
    return this.files().length > 0 && !this.problem() && !!this.name.trim() && !this.submitting();
  }

  totalSize(): string {
    const mb = this.files().reduce((a, f) => a + f.size, 0) / 1e6;
    return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(mb * 1000).toFixed(0)} KB`;
  }

  submit() {
    if (!this.canSubmit) return;
    this.submitting.set(true);
    this.error.set(null);
    this.jobs.importModel(this.data.projectId, this.variant, this.name.trim(), this.files(), this.imgsz)
      .subscribe({
        next: job => this.dialogRef.close(job),
        error: err => {
          this.submitting.set(false);
          this.error.set(err.message || '업로드에 실패했습니다.');
        },
      });
  }

  close() {
    this.dialogRef.close();
  }
}

/** 끌어다 놓은 파일과 폴더(하위 폴더 포함)의 파일을 모두 모읍니다 */
export async function filesFromDrop(dt: DataTransfer): Promise<File[]> {
  const entries = Array.from(dt.items ?? [])
    .map(i => (i as any).webkitGetAsEntry?.())
    .filter(Boolean);
  if (!entries.length) return Array.from(dt.files ?? []);
  const out: File[] = [];
  const walk = async (entry: any, depth: number): Promise<void> => {
    if (entry.isFile) {
      out.push(await new Promise<File>((res, rej) => entry.file(res, rej)));
    } else if (entry.isDirectory && depth < 4) {
      const reader = entry.createReader();
      // readEntries 는 한 번에 일부만 주므로 빈 배열이 나올 때까지 반복
      for (;;) {
        const batch: any[] = await new Promise((res, rej) => reader.readEntries(res, rej));
        if (!batch.length) break;
        for (const e of batch) await walk(e, depth + 1);
      }
    }
  };
  for (const e of entries) await walk(e, 0);
  return out;
}
