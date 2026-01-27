import { Injectable, signal } from '@angular/core';
import { IMLflowRun } from './apis/models/experiment.model';

@Injectable({
  providedIn: 'root',
})
export class Model {

  // 학습 가능한 데이터셋 경로를 저장하는 변수
  selectedDatasetPath = signal<string>('');
  
  // 경로에서 모델 타입을 추론하여 저장하는 변수
  inferredModelName = signal<string | null>(null);

  updatePath(path: string) {
    this.selectedDatasetPath.set(path);

    const pathParts = path.split('/');
    const datasetsIndex = pathParts.findIndex(p => p === 'datasets');

    if (datasetsIndex !== -1 && pathParts[datasetsIndex + 1]) {
      const modelType = pathParts[datasetsIndex + 1];
      this.inferredModelName.set(modelType);
    } else {
      this.inferredModelName.set(null);
    }
  }

  calculateBestRunId(runs: IMLflowRun[], metricKey: string = 'metrics/mAP50_B'): string | null {
    if (!runs || runs.length === 0) return null;

    const finishedRuns = runs.filter(r => r.status === 'FINISHED');
    if (finishedRuns.length === 0) return null;

    const best = finishedRuns.reduce((prev, current) => {
      const prevVal = prev.metrics[metricKey] || 0;
      const currVal = current.metrics[metricKey] || 0;
      return (prevVal > currVal) ? prev : current;
    });

    return best.run_id;
  }

}
