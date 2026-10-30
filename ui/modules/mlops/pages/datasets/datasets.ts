import { Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';
import { DatasetApi } from '../../services/apis/dataset';
import { Project } from '../../services/apis/project';
import { Notification } from '../../services/notification';
import { IProject } from '../../services/apis/models/project.model';
import {
  DATASET_TASK_LABELS, DatasetTask, IDatasetVersion, IPresignedFile, IUploadSession,
} from '../../services/apis/models/dataset.model';

interface PickedFile {
  path: string;
  file: File;
}

const NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const SKIP_FILES = new Set(['.DS_Store', 'Thumbs.db', 'desktop.ini']);
const PRESIGN_BATCH = 1000;
const CONCURRENCY = 4;
const RETRIES = 3;

class UploadCanceled extends Error {}

@Component({
  selector: 'app-datasets-page',
  standalone: false,
  templateUrl: './datasets.html',
  styleUrl: './datasets.scss',
})
export class DatasetsPage implements OnInit, OnDestroy {
  private readonly api = inject(DatasetApi);
  private readonly projectService = inject(Project);
  private readonly notify = inject(Notification);

  readonly taskLabels = DATASET_TASK_LABELS;
  readonly tasks = Object.keys(DATASET_TASK_LABELS) as DatasetTask[];
  readonly layoutHints: Record<DatasetTask, string[]> = {
    detection: [
      'images/train, images/val (필수), images/test (선택) 에 이미지(jpg/png 등)',
      'labels/<같은 분할>/<이미지 이름>.txt — YOLO 형식 "클래스 cx cy w h" (0~1)',
      '클래스 이름은 data.yaml (또는 dataset.yaml) 의 names (선택)',
    ],
    recognition: [
      'train_list.txt, val_list.txt (필수), test_list.txt (선택)',
      '각 줄: "<이미지 상대경로><TAB><정답>" (UTF-8, BOM 허용)',
      '이미지는 목록에 적은 상대경로에 둡니다 (예: images/...)',
    ],
    e2e: [
      'labels.txt — 각 줄: "<이미지 상대경로><TAB><패널><TAB><슬롯 1~6><TAB><정답>"',
      '이미지 하나가 패널 하나인 패널 이미지 (예: images/...)',
      'roi_config.json 이 있으면 전체 프레임 이미지로 보고 패널 좌표대로 잘라 평가',
    ],
  };

  projects = signal<IProject[]>([]);
  projectId = signal<number | null>(null);
  versions = signal<IDatasetVersion[]>([]);
  taskFilter = signal<DatasetTask | ''>('');
  loading = signal(false);
  selectedId = signal<number | null>(null);
  logs = signal<Record<number, string>>({});
  logLoading = signal<number | null>(null);

  filtered = computed(() => {
    const t = this.taskFilter();
    return t ? this.versions().filter(v => v.task === t) : this.versions();
  });
  selected = computed(() => this.versions().find(v => v.id === this.selectedId()) ?? null);

  // 업로드 패널
  showUpload = signal(false);
  session = signal<IUploadSession | null>(null);
  form = { name: '', task: 'detection' as DatasetTask, description: '' };
  picked = signal<PickedFile[]>([]);
  pickedBytes = computed(() => this.picked().reduce((s, f) => s + f.file.size, 0));
  uploading = signal(false);
  doneBytes = signal(0);
  doneFiles = signal(0);
  progress = computed(() => {
    const total = this.pickedBytes();
    return total ? Math.min(100, (this.doneBytes() / total) * 100) : 0;
  });
  private aborters = new Set<AbortController>();
  private canceled = false;
  private pollTimer: any = null;

  ngOnInit() {
    this.projectService.getProjects().subscribe({
      next: list => {
        this.projects.set(list);
        if (list.length) this.onProjectChange(list[0].id);
      },
      error: () => this.notify.showError('프로젝트 목록을 불러오지 못했습니다.'),
    });
  }

  ngOnDestroy() {
    this.stopPolling();
    this.cancelUpload();
  }

  onProjectChange(id: number) {
    this.projectId.set(id);
    this.selectedId.set(null);
    this.refresh();
  }

  refresh(silent = false) {
    const pid = this.projectId();
    if (!pid) return;
    if (!silent) this.loading.set(true);
    this.api.listVersions({ project_id: pid }).subscribe({
      next: list => {
        this.versions.set(list);
        this.loading.set(false);
        this.updatePolling();
      },
      error: err => {
        this.loading.set(false);
        if (!silent) this.notify.showError(err.message);
      },
    });
  }

  // 검사 중인 버전이 있으면 3초마다 목록 갱신
  private updatePolling() {
    const active = this.versions().some(v => v.status === 'VALIDATING');
    if (active && !this.pollTimer) {
      this.pollTimer = setInterval(() => this.refresh(true), 3000);
    } else if (!active) {
      this.stopPolling();
    }
  }

  private stopPolling() {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = null;
  }

  toggleRow(v: IDatasetVersion) {
    this.selectedId.set(this.selectedId() === v.id ? null : v.id);
  }

  loadLogs(v: IDatasetVersion) {
    this.logLoading.set(v.id);
    this.api.getLogs(v.id).subscribe({
      next: text => {
        this.logs.update(m => ({ ...m, [v.id]: text || '(로그 없음)' }));
        this.logLoading.set(null);
      },
      error: err => {
        this.logs.update(m => ({ ...m, [v.id]: `로그를 불러오지 못했습니다: ${err.message}` }));
        this.logLoading.set(null);
      },
    });
  }

  onDelete(v: IDatasetVersion) {
    const label = v.version ? `${v.name} v${v.version}` : `${v.name} (업로드 세션)`;
    if (!confirm(`${label} 을(를) 삭제할까요? 저장된 파일도 함께 지워집니다.`)) return;
    this.api.deleteVersion(v.id).subscribe({
      next: () => {
        this.notify.showSuccess('삭제했습니다.');
        if (this.selectedId() === v.id) this.selectedId.set(null);
        if (this.session()?.id === v.id) this.closeUpload();
        this.refresh();
      },
      error: err => this.notify.showError(err.message),
    });
  }

  onRevalidate(v: IDatasetVersion) {
    this.api.validate(v.id).subscribe({
      next: () => {
        this.notify.showInfo('검사를 시작했습니다.');
        this.refresh();
      },
      error: err => this.notify.showError(err.message),
    });
  }

  // ------------------------------------------------------------ 업로드 패널
  openNewUpload() {
    if (this.uploading()) return;
    this.session.set(null);
    this.form = { name: '', task: 'detection', description: '' };
    this.resetPicked();
    this.showUpload.set(true);
  }

  resumeUpload(v: IDatasetVersion) {
    if (this.uploading()) return;
    this.api.getUpload(v.id).subscribe({
      next: s => {
        this.session.set(s);
        this.form = { name: s.name, task: s.task, description: s.description ?? '' };
        this.resetPicked();
        this.showUpload.set(true);
      },
      error: err => this.notify.showError(err.message),
    });
  }

  closeUpload() {
    if (this.uploading()) return;
    this.showUpload.set(false);
    this.session.set(null);
    this.resetPicked();
  }

  private resetPicked() {
    this.picked.set([]);
    this.doneBytes.set(0);
    this.doneFiles.set(0);
  }

  get nameValid(): boolean {
    return NAME_PATTERN.test(this.form.name);
  }

  onFolderPicked(event: Event) {
    const input = event.target as HTMLInputElement;
    const list: PickedFile[] = [];
    for (const file of Array.from(input.files ?? [])) {
      const rel = (file as any).webkitRelativePath || file.name;
      // 고른 폴더 이름(첫 경로)을 빼서 데이터셋 루트 기준 경로로 만듦
      const parts = rel.split('/');
      const path = parts.length > 1 ? parts.slice(1).join('/') : parts[0];
      const base = parts[parts.length - 1];
      if (SKIP_FILES.has(base) || parts.some((p: string) => p.startsWith('.'))) continue;
      list.push({ path, file });
    }
    list.sort((a, b) => a.path.localeCompare(b.path));
    this.picked.set(list);
    this.doneBytes.set(0);
    this.doneFiles.set(0);
    input.value = '';
  }

  /** 세션이 없으면 만들고 돌려줍니다. */
  private async ensureSession(): Promise<IUploadSession> {
    const current = this.session();
    if (current) return current;
    const created = await firstValueFrom(this.api.createUpload({
      project_id: this.projectId()!,
      name: this.form.name,
      task: this.form.task,
      description: this.form.description || undefined,
    }));
    this.session.set(created);
    this.refresh(true);
    return created;
  }

  async createSessionOnly() {
    if (!this.nameValid || !this.projectId()) return;
    try {
      await this.ensureSession();
      this.notify.showInfo('업로드 세션을 만들었습니다. CLI 로 올린 뒤 검사를 시작하세요.');
    } catch (err: any) {
      this.notify.showError(err.message);
    }
  }

  async startUpload() {
    const files = this.picked();
    if (!files.length || !this.projectId() || (!this.session() && !this.nameValid)) return;
    this.uploading.set(true);
    this.canceled = false;
    this.doneBytes.set(0);
    this.doneFiles.set(0);
    let sessionId: number | null = null;
    try {
      const s = await this.ensureSession();
      sessionId = s.id;
      for (let i = 0; i < files.length; i += PRESIGN_BATCH) {
        const batch = files.slice(i, i + PRESIGN_BATCH);
        const res = await firstValueFrom(this.api.presign(s.id, batch.map(f => ({ path: f.path, size: f.file.size }))));
        const byPath = new Map(batch.map(f => [f.path, f]));
        const jobs = res.files.map(p => () => this.uploadOne(s.id, p, byPath.get(p.path)!));
        await this.runPool(jobs, CONCURRENCY);
      }
      this.uploading.set(false);
      this.notify.showSuccess(`${files.length}개 파일을 올렸습니다. 검사를 시작합니다.`);
      await this.validateSession();
    } catch (err: any) {
      this.uploading.set(false);
      if (err instanceof UploadCanceled || this.canceled) {
        this.notify.showWarning('업로드를 취소했습니다. 같은 세션으로 이어서 올릴 수 있습니다.');
      } else {
        this.notify.showError(`업로드 실패: ${err?.message ?? err}`);
      }
      if (sessionId) this.refresh(true);
    }
  }

  async validateSession() {
    const s = this.session();
    if (!s) return;
    try {
      await firstValueFrom(this.api.validate(s.id));
      this.notify.showInfo('검사를 시작했습니다. 끝나면 목록에 결과가 표시됩니다.');
      this.showUpload.set(false);
      this.session.set(null);
      this.resetPicked();
      this.selectedId.set(s.id);
      this.refresh();
    } catch (err: any) {
      this.notify.showError(err.message);
    }
  }

  cancelUpload() {
    this.canceled = true;
    this.aborters.forEach(a => a.abort());
    this.aborters.clear();
  }

  private async runPool(jobs: (() => Promise<void>)[], n: number) {
    let next = 0;
    const worker = async () => {
      while (next < jobs.length) {
        if (this.canceled) throw new UploadCanceled();
        const job = jobs[next++];
        await job();
      }
    };
    await Promise.all(Array.from({ length: Math.min(n, jobs.length) }, worker));
  }

  private async uploadOne(sessionId: number, p: IPresignedFile, f: PickedFile) {
    if (p.method === 'PUT') {
      await this.putWithRetry(p.url!, f.file);
      this.doneBytes.update(b => b + f.file.size);
    } else {
      const size = p.part_size!;
      const done: { part_number: number; etag: string }[] = [];
      try {
        for (const part of p.parts ?? []) {
          const start = (part.part_number - 1) * size;
          const blob = f.file.slice(start, Math.min(start + size, f.file.size));
          const etag = await this.putWithRetry(part.url, blob);
          if (!etag) throw new Error('ETag 를 읽지 못했습니다 (저장소 CORS 설정 확인)');
          done.push({ part_number: part.part_number, etag });
          this.doneBytes.update(b => b + blob.size);
        }
        await firstValueFrom(this.api.completeMultipart(sessionId, p.path, p.upload_id!, done));
      } catch (err) {
        this.api.abortMultipart(sessionId, p.path, p.upload_id!).subscribe({ error: () => {} });
        throw err;
      }
    }
    this.doneFiles.update(n => n + 1);
  }

  /** 서명된 URL 로 PUT. 서명을 깨지 않도록 헤더를 따로 붙이지 않습니다. 성공 시 ETag 반환. */
  private async putWithRetry(url: string, body: Blob): Promise<string | null> {
    let lastErr: any;
    for (let attempt = 1; attempt <= RETRIES; attempt++) {
      if (this.canceled) throw new UploadCanceled();
      const ctrl = new AbortController();
      this.aborters.add(ctrl);
      try {
        const res = await fetch(url, { method: 'PUT', body, signal: ctrl.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.headers.get('ETag');
      } catch (err: any) {
        if (this.canceled || err?.name === 'AbortError') throw new UploadCanceled();
        lastErr = err;
        await new Promise(r => setTimeout(r, 500 * attempt));
      } finally {
        this.aborters.delete(ctrl);
      }
    }
    throw lastErr;
  }

  copy(text: string) {
    navigator.clipboard.writeText(text);
    this.notify.showInfo('복사했습니다.');
  }

  // ------------------------------------------------------------ 표시용
  formatSize(bytes?: number | null): string {
    if (bytes === null || bytes === undefined) return '-';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let v = bytes;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i++;
    }
    return `${i === 0 ? v : v.toFixed(1)} ${units[i]}`;
  }

  relTime(s?: string | null): string {
    if (!s) return '-';
    const d = new Date(s);
    return isNaN(d.getTime()) ? '-' : formatDistanceToNow(d, { addSuffix: true, locale: ko });
  }

  pretty(obj: any): string {
    return JSON.stringify(obj, null, 2);
  }

  first50(list?: string[]): string[] {
    return (list ?? []).slice(0, 50);
  }
}
