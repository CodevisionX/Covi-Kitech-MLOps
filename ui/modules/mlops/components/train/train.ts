import { Component, effect, inject, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { Model } from '../../services/model';
import { MODEL_CONFIGS } from '../../configs/model-config';
import { Jobs } from '../../services/apis/job';
import { IJobCreate } from '../../services/apis/models/job.model';
import { Notification } from '../../services/notification';
import { Project } from '../../services/apis/project';
import { IProject } from '../../services/apis/models/project.model';

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

  // 학습 설정 관련 상태
  isSubmitting = false;
  configs = MODEL_CONFIGS;

  selectedModelName: string = '';
  selectedProjectId: number | null = null;
  dynamicParams: any = {};
  projects: IProject[] = [];

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
      }
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
  }

  get isCompatible(): boolean {
    const currentPath = this.modelService.selectedDatasetPath();
    if (!currentPath || !this.selectedModelName) return false;

    const config = this.configs[this.selectedModelName];
    if (!config) return true;
    
    const pathNormalized = currentPath.toLowerCase();
    const requiredKeyword = config.requiredKeyword.toLowerCase();
    
    return pathNormalized.includes(requiredKeyword);

  }

  submitTraining() {
    if (!this.isCompatible) {
      this.notificationService.showError('선택한 모델과 데이터셋이 호환되지 않습니다.');
      return;
    }

    const currentPath = this.modelService.selectedDatasetPath();
    if (!currentPath || !this.selectedModelName || !this.selectedProjectId) {
      this.notificationService.showError('필수 설정이 누락되었습니다.');
      return;
    }

    this.isSubmitting = true;

    const payload: IJobCreate = {
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