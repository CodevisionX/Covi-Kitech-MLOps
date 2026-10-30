import { Component, inject, signal } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { Jobs } from '../../../services/apis/job';
import { IJob } from '../../../services/apis/models/job.model';

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
  readonly data = inject<{ projectId: number; variant?: string }>(MAT_DIALOG_DATA);

  variant = this.data.variant === 'PP-OCRv6' ? 'PP-OCRv6' : 'YOLO26';
  name = 'site-model';
  imgsz = 640;
  files = signal<File[]>([]);
  submitting = signal(false);
  error = signal<string | null>(null);

  readonly recFiles = REC_FILES;

  onVariantChange() {
    this.files.set([]);
    this.error.set(null);
  }

  onFiles(event: Event) {
    const input = event.target as HTMLInputElement;
    this.files.set(Array.from(input.files ?? []));
    input.value = '';
    this.error.set(this.problem());
  }

  /** 올릴 파일 구성이 맞지 않으면 이유를 돌려줍니다 */
  problem(): string | null {
    const files = this.files();
    if (files.length === 0) return null;
    if (this.variant === 'YOLO26') {
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
          this.error.set(err.message || '가져오기에 실패했습니다.');
        },
      });
  }

  close() {
    this.dialogRef.close();
  }
}
