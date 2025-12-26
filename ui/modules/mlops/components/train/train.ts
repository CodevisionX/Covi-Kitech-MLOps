import { Component, inject, OnInit } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router } from '@angular/router';
import { Model } from '../../services/model';
import { MODEL_CONFIGS } from '../../configs/model-config';
import { Training } from '../../services/apis/training';
import { Experiment } from '../../services/apis/experiment';
import { IExperiment } from '../../services/apis/models/experiment.model';

@Component({
  selector: 'app-train',
  standalone: false,
  templateUrl: './train.html',
  styleUrl: './train.scss',
})
export class Train implements OnInit {

  private snackBar = inject(MatSnackBar);
  protected modelService = inject(Model);
  protected readonly training = inject(Training);
  private readonly experiment = inject(Experiment);
  private readonly router = inject(Router);

  // 학습 설정 관련 상태
  isSubmitting = false;
  mlflowRunUrl: string = '';
  configs = MODEL_CONFIGS;
  selectedModelName: string = '';
  dynamicParams: any = {};
  allExperiments: IExperiment[] = [];

  ngOnInit() {
    this.experiment.getAll().subscribe(exps => {
      this.allExperiments = exps;
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

  openMlflow() {
    if (this.mlflowRunUrl) {
      window.open(this.mlflowRunUrl, '_blank');
    }
  }

  submitTraining() {
    const currentPath = this.modelService.selectedDatasetPath();

    if (!currentPath || !this.selectedModelName) {
      this.snackBar.open('❌ 필수 설정이 누락되었습니다.', '닫기', { duration: 3000 });
      return;
    }

    this.isSubmitting = true;

    const payload = {
      dataset: currentPath,
      epochs: this.dynamicParams['epochs'] || 10,
      batch: this.dynamicParams['batch'] || 16,
      model_variant: this.selectedModelName
    };

    this.training.start(payload).subscribe({
      next: (res) => {
        const targetExp = this.allExperiments.find(e => 
          e.name.includes(this.selectedModelName)
        );

        // 1. 알림 표시
        this.snackBar.open(`🚀 학습 요청 완료! (상태: ${res.status})`, '확인', {
          duration: 3000,
          horizontalPosition: 'right',
          verticalPosition: 'top',
        });

        // 2. 바로 목록 페이지로 이동
        this.router.navigate(['/dashboard/models'], {
          queryParams: { 
            algorithm: this.selectedModelName,
            expId: targetExp ? targetExp.experiment_id : null // 찾은 ID를 넣어줌
          }
        });
      },
      error: (err) => {
        this.isSubmitting = false;
        this.snackBar.open('❌ 학습 요청에 실패했습니다.', '닫기');
      }
    });
  }
}