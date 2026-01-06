import { Component, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { Deployment } from '../../services/apis/deployment';
import { Notification } from '../../services/notification';
import { IDeployment } from '../../services/apis/models/deployment.model';
import { Jobs } from '../../services/apis/job';
import { IJob } from '../../services/apis/models/job.model';

@Component({
  selector: 'app-model-validation',
  standalone: false,
  templateUrl: './model-validation.html',
  styleUrl: './model-validation.scss',
})
export class ModelValidation implements OnInit {

  private route = inject(ActivatedRoute);
  private readonly jobService = inject(Jobs);
  private readonly deploymentService = inject(Deployment);
  private readonly notificationService = inject(Notification);
  private readonly sanitizer = inject(DomSanitizer);

  job = signal<IJob | null>(null);
  deployment = signal<IDeployment | null>(null);
  selectedFile = signal<File | null>(null);
  imagePreview = signal<string | null>(null);
  resultImage = signal<string | SafeUrl | null>(null);
  predictionResult = signal<any>(null);
  isTesting = signal<boolean>(false);

  ngOnInit() {
    const deploymentId = this.route.snapshot.paramMap.get('deploymentId');
    
    if (deploymentId) {
      this.loadDeploymentDetail(Number(deploymentId));
    }
  }

  // 서버로부터 배포 상세 정보 로드
  loadDeploymentDetail(deploymentId: number) {
    this.deploymentService.getDeploymentById(deploymentId).subscribe({
      next: (data) => {
        this.deployment.set(data);
        if (data.job_id) {
          this.loadJobDetail(data.job_id);
        }
      },
      error: (err) => {
        this.notificationService.showError('배포 정보를 불러오는데 실패했습니다.');
      }
    });
  }

  loadJobDetail(jobId: number) {
    this.jobService.getJob(jobId).subscribe({
      next: (jobData) => this.job.set(jobData),
      error: (err) => this.notificationService.showError('학습 정보를 불러오지 못했습니다.')
    });
  }

  get paramsArray() {
    const p = this.job()?.params;
    return p ? Object.entries(p) : [];
  }

  // 파일 선택 처리
  onFileSelected(event: any) {
    const file = event.target.files[0];
    if (file) {
      this.preparePreview(file);
    }
  }

  // 드래그 앤 드롭 처리
  onFileDropped(event: DragEvent) {
    event.preventDefault();
    const file = event.dataTransfer?.files[0];
    if (file) {
      this.preparePreview(file);
    }
  }

  preparePreview(file: File) {
    this.selectedFile.set(file);
    const reader = new FileReader();
    reader.onload = () => this.imagePreview.set(reader.result as string);
    reader.readAsDataURL(file);
    
    // 이전 결과 초기화
    this.resultImage.set(null);
    this.predictionResult.set(null);
  }

  testPredict() {
    const file = this.selectedFile();
    const dep = this.deployment(); 
    if (!file || !dep) return;

    this.isTesting.set(true);

    this.deploymentService.predictVisual(dep.id, file).subscribe({
      next: (blob: Blob) => {
        const objectUrl = URL.createObjectURL(blob);
        const safeUrl = this.sanitizer.bypassSecurityTrustUrl(objectUrl);

        this.resultImage.set(safeUrl);
        this.isTesting.set(false);
        this.notificationService.showSuccess('추론이 완료되었습니다.');
      },
      error: (err) => {
        this.notificationService.showError('추론 중 오류가 발생했습니다.');
        this.isTesting.set(false);
      }
    });
  }

}
