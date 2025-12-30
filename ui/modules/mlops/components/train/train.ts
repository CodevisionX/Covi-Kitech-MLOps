import { Component, inject, OnInit } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router } from '@angular/router';
import { Model } from '../../services/model';
import { MODEL_CONFIGS } from '../../configs/model-config';
import { Jobs } from '../../services/apis/job';
import { IJobCreate } from '../../services/apis/models/job.model';
import { Project } from '../../services/apis/project';
import { IProject } from '../../services/apis/models/project.model';

@Component({
  selector: 'app-train',
  standalone: false,
  templateUrl: './train.html',
  styleUrl: './train.scss',
})
export class Train implements OnInit {

  private snackBar = inject(MatSnackBar);
  protected modelService = inject(Model);
  protected readonly jobService = inject(Jobs);
  private readonly projectService = inject(Project);
  private readonly router = inject(Router);

  // 학습 설정 관련 상태
  isSubmitting = false;
  configs = MODEL_CONFIGS;

  selectedModelName: string = '';
  selectedProjectId: number | null = null;
  dynamicParams: any = {};
  projects: IProject[] = [];

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

  submitTraining() {
    const currentPath = this.modelService.selectedDatasetPath();

    if (!currentPath || !this.selectedModelName || !this.selectedProjectId) {
      this.snackBar.open('❌ 필수 설정이 누락되었습니다.', '닫기', { duration: 3000 });
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
        "stage": "Experimental"
      }
    }
    console.log('Training Payload:', payload);

    this.jobService.createJob(payload).subscribe({
      next: (res) => {
        this.snackBar.open(`🚀 학습 작업이 등록되었습니다! (ID: ${res.id})`, '확인', {
          duration: 3000,
          horizontalPosition: 'right',
          verticalPosition: 'top',
        });

        this.router.navigate(['/dashboard/models'], {
          queryParams: { projectId: this.selectedProjectId }
        });
      },
      error: (err) => {
        console.error(err);
        this.isSubmitting = false;
        this.snackBar.open('❌ 학습 요청에 실패했습니다. (422 오류 시 데이터 구조 확인)', '닫기');
      }
    });
  }
}