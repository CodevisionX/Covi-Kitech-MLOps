import { Component, effect, inject, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { Model } from '../../services/model';
import { MODEL_CONFIGS } from '../../configs/model-config';
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

  protected modelService = inject(Model);
  protected readonly jobService = inject(Jobs);
  private readonly projectService = inject(Project);
  private readonly notificationService = inject(Notification);
  private readonly router = inject(Router);
  private readonly datasetApi = inject(DatasetApi);

  // 학습 설정 관련 상태
  isSubmitting = false;
  configs = MODEL_CONFIGS;

  selectedModelName: string = '';
  selectedProjectId: number | null = null;
  dynamicParams: any = {};
  projects: IProject[] = [];

  // 신규 모델(YOLO26, PP-OCRv6)은 등록된 데이터셋 버전에서 고릅니다
  datasetVersions: IDatasetVersion[] = [];
  selectedVersionId: number | null = null;

  constructor() {
    effect(() => {
      const autoModel = this.modelService.inferredModelName();
      if (autoModel && this.configs[autoModel]) {
        if (this.selectedModelName !== autoModel) {
          this.onModelChange(autoModel);
          this.notificationService.showInfo(`🤖 알고리즘이 자동으로 '${autoModel}'로 설정되었습니다.`);
        }
      }
    })
  }

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

  onProjectChange(projectId: number) {
    this.selectedProjectId = projectId;
    this.loadDatasetVersions();
  }

  loadDatasetVersions() {
    this.selectedVersionId = null;
    this.datasetVersions = [];
    const task = this.requiredTask;
    if (!task || !this.selectedProjectId) return;
    this.datasetApi.listVersions({ project_id: this.selectedProjectId, task, status: 'READY' }).subscribe({
      next: list => {
        this.datasetVersions = list;
        if (list.length > 0) this.selectedVersionId = list[0].id;
      },
      error: err => this.notificationService.showError(err.message),
    });
  }

  onModelChange(modelName: string) {
    this.selectedModelName = modelName;
    const config = this.configs[modelName];

    if (config) {
      this.dynamicParams = {};
      config.parameters.forEach(p => {
        this.dynamicParams[p.name] = p.default;
      });
    }
    this.loadDatasetVersions();
  }

  get isReady(): boolean {
    if (!this.selectedModelName || !this.selectedProjectId) return false;
    return this.requiredTask ? this.selectedVersionId !== null : !!this.modelService.selectedDatasetPath() && this.isCompatible;
  }

  get isCompatible(): boolean {
    if (this.requiredTask) return this.selectedVersionId !== null;
    const currentPath = this.modelService.selectedDatasetPath();
    if (!currentPath || !this.selectedModelName) return false;

    const config = this.configs[this.selectedModelName];
    if (!config) return true;
    
    const pathNormalized = currentPath.toLowerCase();
    const requiredKeyword = config.requiredKeyword.toLowerCase();
    
    return pathNormalized.includes(requiredKeyword);

  }

  submitTraining() {
    if (!this.isReady || !this.selectedProjectId) {
      this.notificationService.showError('모델과 데이터셋을 확인해 주세요.');
      return;
    }

    this.isSubmitting = true;

    const version = this.selectedVersion;
    const currentPath = this.modelService.selectedDatasetPath();
    const payload: IJobCreate = version ? {
      project_id: this.selectedProjectId,
      dataset: '',
      dataset_version_id: version.id,
      model_variant: this.selectedModelName,
      params: { ...this.dynamicParams },
      // dataset_version 태그는 백엔드가 등록 버전 이름으로 기록합니다
      tags: { author: 'KITECH', stage: 'Experimental' },
    } : {
      project_id: this.selectedProjectId,
      dataset: currentPath,
      model_variant: this.selectedModelName,
      params: { ...this.dynamicParams },
      tags: {
        "author": "KITECH", // 개발자 정보
        "dataset_version": "v1.0",
        "stage": "Experimental",
        "dataset_path": currentPath
      }
    }

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