import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { Deployment } from '../../services/apis/deployment';
import { Notification } from '../../services/notification';
import { IDeployment } from '../../services/apis/models/deployment.model';
import { Jobs } from '../../services/apis/job';
import { IJob } from '../../services/apis/models/job.model';
import { switchMap, finalize } from 'rxjs';

const TEP_FAULT_MAP: { [key: number]: string } = {
  0: '정상 운전 (Normal Operation)',
  1: 'A/C 공급 비율 변화 (A/C Feed Ratio, Step Change)',
  2: 'B 구성 성분 변화 (B Composition, Step Change)',
  3: 'D 피드 온도 변화 (D Feed Temp, Step Change)',
  4: '반응기 냉각수 유입 온도 변화 (Reactor Cooling Water Inlet Temp, Step)',
  5: '응축기 냉각수 유입 온도 변화 (Condenser Cooling Water Inlet Temp, Step)',
  6: 'A 피드 손실 (A Feed Loss, Step Change)',
  7: 'C 헤더 압력 손실 (C Header Pressure Loss, Step Change)',
  8: 'A/B/C 피드 성분 랜덤 변화 (A, B, C Feed Composition, Random Variation)',
  9: 'D 피드 온도 랜덤 변화 (D Feed Temp, Random Variation)',
  10: 'C 피드 온도 랜덤 변화 (C Feed Temp, Random Variation)',
  11: '반응기 냉각수 유입 온도 랜덤 변화 (Reactor Cooling Water Inlet Temp, Random)',
  12: '응축기 냉각수 유입 온도 랜덤 변화 (Condenser Cooling Water Inlet Temp, Random)',
  13: '반응 속도론 완만한 드리프트 (Reaction Kinetics, Slow Drift)',
  14: '반응기 냉각수 밸브 고착 (Reactor Cooling Water Valve, Sticking)',
  15: '응축기 냉각수 밸브 고착 (Condenser Cooling Water Valve, Sticking)',
  16: '알 수 없는 이상 1 (Unknown Disturbance - Random Variation)',
  17: '알 수 없는 이상 2 (Unknown Disturbance - Random Variation)',
  18: '알 수 없는 이상 3 (Unknown Disturbance - Step Change)',
  19: '알 수 없는 이상 4 (Unknown Disturbance - Random Variation)',
  20: '알 수 없는 이상 5 (Unknown Disturbance - Random Variation)',
  21: '밸브 4 고착 이상 (The Valve 4 Sticking - Fixed Position)'
};

const GT_GRADE_MAP: { [key: number]: string } = {
  1: '최적 운전 등급 (Good)',
  2: '배출치 주의 등급 (Warning)',
  3: '배출치 위험 등급 (Danger)'
};


@Component({
  selector: 'app-model-validation-cnn',
  standalone: false,
  templateUrl: './model-validation-cnn.html',
  styleUrl: './model-validation-cnn.scss',
})
export class ModelValidationCnn implements OnInit {
  private route = inject(ActivatedRoute);
  private readonly jobService = inject(Jobs);
  private readonly deploymentService = inject(Deployment);
  private readonly notificationService = inject(Notification);

  job = signal<IJob | null>(null);
  deployment = signal<IDeployment | null>(null);
  selectedFile = signal<File | null>(null);
  selectedFileName = signal<string | null>(null);
  extractedData = signal<any>(null);
  predictionResult = signal<any>(null);
  isTesting = signal<boolean>(false);

  analysisType = computed(() => {
    const datasetName = this.job()?.dataset?.toLowerCase() || '';
    return datasetName.includes('tep') ? '이상 분류 (Classification)' : '배출량 예측 (Regression)';
  });

  // [추가] 결과 해석 로직: 인덱스를 사람이 이해할 수 있는 텍스트로 변환
  interpretedResult = computed(() => {
    const results = this.detailedResults();
    if (results.length === 0) return null;
    return results[results.length - 1].label; // 마지막 시점의 결과를 대표로 표시
  });

  isAnomaly = computed(() => {
    const res = this.predictionResult();
    if (!res || !res.prediction) return false;
    const predValue = Array.isArray(res.prediction) ? res.prediction[0] : res.prediction;
    return Number(predValue) > 0;
  });

  detailedResults = computed(() => {
    const res = this.predictionResult();
    if (!res || !res.metadata || !res.metadata.source_indices) return [];

    const dataset = this.job()?.dataset?.toLowerCase() || '';
    const indices = res.metadata.source_indices; // [50, 51, 52]
    const predictions = res.prediction;          // [0, 0, 7]

    // 인덱스와 결과를 1:1로 매핑
    return indices.map((idx: number, i: number) => {
      const val = predictions[i];
      let label = '';

      if (dataset.includes('tep')) {
        label = TEP_FAULT_MAP[val] || `Fault ${val}`;
      } else {
        label = GT_GRADE_MAP[val] || `Grade ${val}`;
      }

      return { index: idx, label: label, raw: val };
    });
  });

  get paramsArray() {
    const p = this.job()?.params;
    if (!p) return [];

    // Object.entries 결과를 명확한 객체 형태로 매핑합니다.
    return Object.entries(p).map(([key, value]) => ({
      key: key,
      value: value
    }));
  }

  ngOnInit() {
    const deploymentId = this.route.snapshot.paramMap.get('deploymentId');
    if (deploymentId) {
      this.loadDeploymentDetail(Number(deploymentId));
    }
  }

  loadDeploymentDetail(deploymentId: number) {
    this.deploymentService.getDeploymentById(deploymentId).subscribe({
      next: (data) => {
        this.deployment.set(data);
        if (data.job_id) this.loadJobDetail(data.job_id);
      },
      error: () => this.notificationService.showError('배포 정보를 불러오지 못했습니다.')
    });
  }

  loadJobDetail(jobId: number) {
    this.jobService.getJob(jobId).subscribe({
      next: (jobData) => this.job.set(jobData),
      error: () => this.notificationService.showError('학습 상세 정보를 불러오지 못했습니다.')
    });
  }

  onNpyFileSelected(event: any) {
    const file = event.target.files[0];
    if (file) {
      this.selectedFile.set(file);
      this.selectedFileName.set(file.name);
      this.extractedData.set(null);
      this.predictionResult.set(null);
    }
  }

  // [개선] 추출과 추론을 한 번에 실행하는 통합 로직
  runFullValidation() {
    const file = this.selectedFile();
    const dep = this.deployment();
    if (!file || !dep) {
      this.notificationService.showError('먼저 검증할 .npy 파일을 업로드하세요.');
      return;
    }

    this.isTesting.set(true);

    // 1. 샘플 추출 시도
    this.deploymentService.extractSample(dep.id, file).pipe(
      // 2. 추출 성공 시 바로 추론 API 호출 (switchMap 활용)
      switchMap(res => {
        this.extractedData.set(res.data);
        return this.deploymentService.predictData(dep.id, { 
          data: res.data, 
          extracted_indices: res.extracted_indices 
        });
      }),
      // 로딩 상태 해제
      finalize(() => this.isTesting.set(false))
    ).subscribe({
      next: (res) => {
        this.predictionResult.set(res);
        this.notificationService.showSuccess('분석이 완료되었습니다.');
      },
      error: (err) => {
        this.notificationService.showError('검증 과정 중 오류가 발생했습니다. 파일 형식을 확인하세요.');
        console.error(err);
      }
    });
  }
}