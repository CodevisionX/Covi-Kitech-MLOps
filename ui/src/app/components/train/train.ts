import { Component, inject } from '@angular/core';
import { Api } from '../../core/services/api';
import { MODEL_CONFIGS } from '../../core/configs/model-config';
import { Model } from '../../core/services/model';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TerminalService } from '../../core/services/terminal';
import { Router } from '@angular/router';

@Component({
  selector: 'app-train',
  standalone: false,
  templateUrl: './train.html',
  styleUrl: './train.scss',
})
export class Train {

  private snackBar = inject(MatSnackBar);
  private terminalService = inject(TerminalService);
  protected modelService = inject(Model);
  protected apiService = inject(Api);
  private readonly router = inject(Router);

  // 학습 설정 관련 상태
  isSubmitting = false;
  mlflowRunUrl: string = '';
  configs = MODEL_CONFIGS;
  selectedModelName: string = '';
  dynamicParams: any = {};


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

    this.apiService.startTraining(payload).subscribe({
      next: (res) => {
        this.mlflowRunUrl = res.mlflow_url;

        // ✅ 전역 서비스에 스트리밍 시작 명령 전달
        this.terminalService.startStreaming(res.container_id);

        this.snackBar.open(`🚀 학습 시작!`, '확인', {
          duration: 3000,
          horizontalPosition: 'right',
          verticalPosition: 'top',
        });

        this.router.navigate(['/models'], {
          queryParams: { algorithm: payload.model_variant }
        });
      },
      error: (err) => {
        this.isSubmitting = false;
        this.snackBar.open('❌ 학습 요청에 실패했습니다.', '닫기');
      },
      complete: () => {
        this.isSubmitting = false;
      }
    });
  }
}