import { Component, inject, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { MODEL_CONFIGS, ModelParameter } from '../../configs/model-config';
import { Jobs } from '../../services/apis/job';
import { IJobCreate } from '../../services/apis/models/job.model';
import { Notification } from '../../services/notification';
import { Project } from '../../services/apis/project';
import { IProject } from '../../services/apis/models/project.model';
import { DatasetApi } from '../../services/apis/dataset';
import { IDatasetVersion } from '../../services/apis/models/dataset.model';

@Component({
  selector: 'app-train',
  standalone: false,
  templateUrl: './train.html',
  styleUrl: './train.scss',
})
export class Train implements OnInit {

  protected readonly jobService = inject(Jobs);
  private readonly projectService = inject(Project);
  private readonly notificationService = inject(Notification);
  private readonly router = inject(Router);
  private readonly datasetApi = inject(DatasetApi);

  // 학습 설정 관련 상태
  isSubmitting = false;
  configs = MODEL_CONFIGS;
  /** select 의 '직접 입력' 항목 값 */
  readonly CUSTOM = '__custom__';
  /** '직접 입력'을 고른 파라미터 */
  customParams: Record<string, boolean> = {};

  selectedModelName: string = '';
  selectedProjectId: number | null = null;
  dynamicParams: any = {};
  projects: IProject[] = [];

  // 신규 모델(YOLO26, PP-OCRv6)은 등록된 데이터셋 버전에서 고릅니다.
  // 학습용 종류(검출·인식)의 버전을 모두 보여 주고, 고른 버전의 종류에 맞는 모델을 자동으로 정합니다.
  datasetVersions: IDatasetVersion[] = [];
  selectedVersionId: number | null = null;

  /** 데이터셋 종류 -> 그 종류로 학습하는 모델들 (설정에서 만들므로 모델이 늘어도 그대로 동작) */
  readonly modelsByTask: Record<string, string[]> = Object.entries(MODEL_CONFIGS)
    .filter(([, c]) => !!c.datasetTask)
    .reduce((acc, [name, c]) => {
      (acc[c.datasetTask!] ||= []).push(name);
      return acc;
    }, {} as Record<string, string[]>);
  readonly taskLabels: Record<string, string> = { detection: '검출', recognition: '인식', timeseries: '시계열' };

  ngOnInit() {
    this.loadProjects();
  }

  loadProjects() {
    this.projectService.getProjects().subscribe(projs => {
      this.projects = projs;
      // 테스트 편의를 위해 첫 번째 프로젝트 자동 선택
      if (projs.length > 0) {
        this.selectedProjectId = projs[0].id;
        this.loadDatasetVersions();
      }
    });
  }

  get requiredTask(): string | undefined {
    return this.configs[this.selectedModelName]?.datasetTask;
  }

  get selectedVersion(): IDatasetVersion | undefined {
    return this.datasetVersions.find(v => v.id === this.selectedVersionId);
  }

  /** 등록 데이터셋 카드를 보일지: 신규 모델을 골랐거나, 아직 아무 모델도 고르지 않았을 때 */
  get showVersionCard(): boolean {
    return !!this.requiredTask || !this.selectedModelName;
  }

  /** 종류별로 묶은 버전 목록 (선택 목록의 그룹) */
  get versionGroups(): { task: string; label: string; versions: IDatasetVersion[] }[] {
    return Object.keys(this.modelsByTask).map(task => ({
      task,
      label: `${this.taskLabels[task] || task} → ${this.modelsByTask[task].join(', ')}`,
      versions: this.datasetVersions.filter(v => v.task === task),
    })).filter(g => g.versions.length);
  }

  /** 데이터셋을 고르면 그 종류에 맞는 모델로 맞춤 (이미 맞는 모델이면 그대로 둠) */
  onVersionChange(id: number) {
    this.selectedVersionId = id;
    const task = this.selectedVersion?.task;
    const candidates = task ? this.modelsByTask[task] || [] : [];
    if (!candidates.length || candidates.includes(this.selectedModelName)) return;
    this.onModelChange(candidates[0]);
    this.notificationService.showInfo(`데이터셋 종류(${this.taskLabels[task!] || task})에 맞춰 '${candidates[0]}' 모델로 설정했습니다.`);
  }

  onProjectChange(projectId: number) {
    this.selectedProjectId = projectId;
    this.loadDatasetVersions();
  }

  /** 학습에 쓸 수 있는 종류(검출·인식)의 등록 완료 버전을 모두 불러옴 */
  loadDatasetVersions() {
    this.selectedVersionId = null;
    this.datasetVersions = [];
    if (!this.selectedProjectId) return;
    this.datasetApi.listVersions({ project_id: this.selectedProjectId, status: 'READY' }).subscribe({
      next: list => {
        this.datasetVersions = list.filter(v => !!this.modelsByTask[v.task]);
        this.selectMatchingVersion();
      },
      error: err => this.notificationService.showError(err.message),
    });
  }

  /** 모델을 직접 바꿨을 때 선택된 버전이 그 모델과 맞지 않으면 맞는 버전 중 최신으로 바꿈 */
  private selectMatchingVersion() {
    const task = this.requiredTask;
    if (!task) return;
    if (this.selectedVersion?.task === task) return;
    this.selectedVersionId = this.datasetVersions.find(v => v.task === task)?.id ?? null;
  }

  onModelChange(modelName: string) {
    this.selectedModelName = modelName;
    const config = this.configs[modelName];

    if (config) {
      this.dynamicParams = {};
      this.customParams = {};
      config.parameters.forEach(p => {
        this.dynamicParams[p.name] = p.default;
      });
    }
    this.selectMatchingVersion();
  }

  get isReady(): boolean {
    return !!this.selectedModelName && !!this.selectedProjectId && !!this.requiredTask
      && this.selectedVersion?.task === this.requiredTask && !this.hasParamError;
  }

  onSelectParam(p: ModelParameter, value: any) {
    if (value !== this.CUSTOM) {
      this.dynamicParams[p.name] = value;
      return;
    }
    // '직접 입력': 지금 값을 그대로 두고 같은 자리의 입력 칸에서 고치게 함
    this.customParams[p.name] = true;
    setTimeout(() => (document.getElementById('custom-' + p.name) as HTMLInputElement | null)?.select());
  }

  /** 목록으로 돌아가기: 입력한 값이 목록에 있으면 유지, 없으면 기본값 */
  backToList(p: ModelParameter) {
    this.customParams[p.name] = false;
    if (!p.options?.includes(Number(this.dynamicParams[p.name]))) this.dynamicParams[p.name] = p.default;
  }

  /** 직접 입력한 값이 정수이고 범위 안인지 */
  customValid(p: ModelParameter): boolean {
    const v = Number(this.dynamicParams[p.name]);
    return !!p.custom && Number.isInteger(v) && v >= p.custom.min && v <= p.custom.max;
  }

  get hasParamError(): boolean {
    const params = this.configs[this.selectedModelName]?.parameters ?? [];
    return params.some(p => this.customParams[p.name] && !this.customValid(p));
  }

  submitTraining() {
    if (!this.isReady || !this.selectedProjectId) {
      this.notificationService.showError('모델과 데이터셋을 확인해 주세요.');
      return;
    }

    this.isSubmitting = true;

    const version = this.selectedVersion!;
    const payload: IJobCreate = {
      project_id: this.selectedProjectId,
      dataset: '',
      dataset_version_id: version.id,
      model_variant: this.selectedModelName,
      params: { ...this.dynamicParams },
      // dataset_version 태그는 백엔드가 등록 버전 이름으로 기록합니다
      tags: { author: 'KITECH', stage: 'Experimental' },
    };

    this.jobService.createJob(payload).subscribe({
      next: (res) => {
        this.isSubmitting = false;
        this.notificationService.showSuccess(`학습 큐에 등록되었습니다! (ID: ${res.id})`);

        this.router.navigate(['/dashboard/models'], {
          queryParams: { projectId: this.selectedProjectId, variant: this.selectedModelName }
        });
      },
      error: (err) => {
        console.error(err);
        this.isSubmitting = false;
        this.notificationService.showError('학습 요청 실패: ' + (err.message || '서버 오류'));
      }
    });
  }
}