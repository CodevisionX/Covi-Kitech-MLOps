import { Component, computed, inject, OnDestroy, OnInit, signal, TemplateRef, ViewChild } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';
import { DatasetApi } from '../../services/apis/dataset';
import { Project } from '../../services/apis/project';
import { Notification } from '../../services/notification';
import { IProject } from '../../services/apis/models/project.model';
import { DATASET_GUIDES } from './dataset-guides';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { DatasetGuideDialog } from '../../components/dialogs/dataset-guide/dataset-guide';
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
  private readonly dialog = inject(MatDialog);

  /** 업로드 가이드 모달 (종류를 주면 그 탭으로 엶) */
  openGuide(task?: DatasetTask) {
    // 업로드 중에 열면 폴더 준비 단계부터 보여 줌
    this.dialog.open(DatasetGuideDialog, {
      data: { task, step: task ? 1 : 0 },
      width: '1280px', maxWidth: '96vw', height: '88vh', autoFocus: false,
    });
  }

  readonly taskLabels = DATASET_TASK_LABELS;
  readonly tasks = Object.keys(DATASET_TASK_LABELS) as DatasetTask[];
  readonly guides = DATASET_GUIDES;

  /** 고른 폴더에 필수 경로가 있는지 (zip 하나만 올리면 서버에서 풀어 검사하므로 건너뜀) */
  structureCheck = computed(() => {
    const files = this.picked();
    if (!files.length) return null;
    if (files.length === 1 && files[0].path.toLowerCase().endsWith('.zip')) return { zip: true, items: [], ok: true };
    const paths = files.map(f => f.path);
    const items = DATASET_GUIDES[this.taskSig()].required.map(r => ({
      ...r,
      found: r.kind === 'file' ? paths.includes(r.path) : paths.some(p => p.startsWith(r.path + '/')),
    }));
    return { zip: false, items, ok: items.every(i => i.found) };
  });
  /** 템플릿 form.task 를 계산값에서 쓰기 위한 신호 */
  taskSig = signal<DatasetTask>('detection');

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
  /** 종류 탭: 학습용 종류를 먼저, 평가용(E2E)을 마지막에 */
  readonly tabOrder: DatasetTask[] = ['detection', 'recognition', 'timeseries', 'e2e'];
  readonly tabLabels: Record<DatasetTask, string> = {
    detection: '검출', recognition: '인식', timeseries: '시계열', e2e: 'E2E 평가',
  };
  taskCounts = computed(() => {
    const c: Record<string, number> = {};
    for (const v of this.versions()) c[v.task] = (c[v.task] || 0) + 1;
    return c;
  });

  // 업로드 모달
  @ViewChild('uploadTpl') private uploadTpl!: TemplateRef<unknown>;
  private uploadRef: MatDialogRef<unknown> | null = null;
  showUpload = signal(false);

  private setUploadOpen(open: boolean) {
    this.showUpload.set(open);
    if (open && !this.uploadRef) {
      // 닫기는 X 버튼으로만 (파일 선택창 클릭이 배경으로 전달되어 닫히는 일 방지)
      this.uploadRef = this.dialog.open(this.uploadTpl, {
        width: '1200px', maxWidth: '96vw', maxHeight: '92vh', disableClose: true, autoFocus: false,
        panelClass: 'dataset-upload-panel',
      });
      this.uploadRef.afterClosed().subscribe(() => (this.uploadRef = null));
    } else if (!open && this.uploadRef) {
      this.uploadRef.close();
    }
  }
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
    // 종류 탭을 보고 있으면 그 종류로 시작
    const task: DatasetTask = this.taskFilter() || 'detection';
    this.form = { name: '', task, description: '' };
    this.taskSig.set(task);
    this.resetPicked();
    this.setUploadOpen(true);
  }

  resumeUpload(v: IDatasetVersion) {
    if (this.uploading()) return;
    this.api.getUpload(v.id).subscribe({
      next: s => {
        this.session.set(s);
        this.form = { name: s.name, task: s.task, description: s.description ?? '' };
        this.taskSig.set(s.task);
        this.resetPicked();
        this.setUploadOpen(true);
      },
      error: err => this.notify.showError(err.message),
    });
  }

  closeUpload() {
    if (this.uploading()) return;
    this.setUploadOpen(false);
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
      list.push({ path: parts.length > 1 ? parts.slice(1).join('/') : parts[0], file });
    }
    input.value = '';
    this.setPicked(list);
  }

  // ------------------------------------------------------------ 끌어다 놓기
  dragOver = signal(false);

  onDragOver(event: DragEvent) {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
    this.dragOver.set(true);
  }

  onDragLeave(event: DragEvent) {
    // 안쪽 요소로 옮겨 갈 때 생기는 leave 는 무시
    const to = event.relatedTarget as Node | null;
    if (!to || !(event.currentTarget as HTMLElement).contains(to)) this.dragOver.set(false);
  }

  /** 등록 버튼에 놓으면 등록 모달을 열고, 모달의 업로드 칸에 놓으면 그대로 파일을 고릅니다. */
  async onDrop(event: DragEvent) {
    event.preventDefault();
    this.dragOver.set(false);
    if (this.uploading()) return;
    // 항목 목록은 drop 이벤트 안에서만 읽을 수 있어 먼저 꺼내 둠
    const entries = Array.from(event.dataTransfer?.items ?? [])
      .map(i => (i as any).webkitGetAsEntry?.())
      .filter((e: any) => !!e);
    if (!entries.length) return;
    if (!this.showUpload()) this.openNewUpload();
    try {
      // 폴더 하나를 놓으면 그 폴더 안을 데이터셋 루트로 봄 (폴더 선택과 같은 규칙)
      const roots = entries.length === 1 && entries[0].isDirectory ? await readDir(entries[0]) : entries;
      const list: PickedFile[] = [];
      for (const e of roots) await collect(e, '', list);
      this.setPicked(list);
    } catch (e: any) {
      this.notify.showError(`끌어다 놓은 파일을 읽지 못했습니다: ${e?.message || e}`);
    }
  }

  private setPicked(all: PickedFile[]) {
    const list = all.filter(f => {
      const parts = f.path.split('/');
      return !SKIP_FILES.has(parts[parts.length - 1]) && !parts.some(p => p.startsWith('.'));
    });
    list.sort((a, b) => a.path.localeCompare(b.path));
    this.picked.set(list);
    this.doneBytes.set(0);
    this.doneFiles.set(0);
    if (!list.length) this.notify.showWarning('올릴 파일이 없습니다.');
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
    const check = this.structureCheck();
    if (check && !check.ok) {
      const missing = check.items.filter(i => !i.found).map(i => i.path).join(', ');
      if (!confirm(`필수 경로가 없습니다: ${missing}\n그래도 올리면 검사에서 실패합니다. 계속할까요?`)) return;
    }
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
      this.setUploadOpen(false);
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

/** 끌어다 놓은 폴더의 바로 아래 항목 (readEntries 는 한 번에 일부만 주므로 빌 때까지 반복) */
function readDir(dir: any): Promise<any[]> {
  const reader = dir.createReader();
  const out: any[] = [];
  return new Promise((resolve, reject) => {
    const next = () => reader.readEntries((batch: any[]) => {
      if (!batch.length) return resolve(out);
      out.push(...batch);
      next();
    }, reject);
    next();
  });
}

async function collect(entry: any, prefix: string, out: PickedFile[]) {
  if (entry.isFile) {
    const file: File = await new Promise((resolve, reject) => entry.file(resolve, reject));
    out.push({ path: prefix + entry.name, file });
  } else if (entry.isDirectory) {
    for (const child of await readDir(entry)) await collect(child, `${prefix}${entry.name}/`, out);
  }
}
