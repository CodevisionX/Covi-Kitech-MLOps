import { Component, inject, signal } from '@angular/core';
import { MAT_DIALOG_DATA } from '@angular/material/dialog';
import { DATASET_GUIDES } from '../../../pages/datasets/dataset-guides';
import { DatasetTask } from '../../../services/apis/models/dataset.model';

/** 데이터셋 업로드 가이드: 단계별로 따라 읽는 안내 문서 */
@Component({
  selector: 'app-dataset-guide-dialog',
  standalone: false,
  templateUrl: './dataset-guide.html',
  styleUrl: './dataset-guide.scss',
})
export class DatasetGuideDialog {
  readonly data = inject<{ task?: DatasetTask; step?: number } | null>(MAT_DIALOG_DATA, { optional: true });

  readonly guides = DATASET_GUIDES;
  /** 학습용 종류 먼저, 평가용(E2E) 마지막 */
  readonly tasks: DatasetTask[] = ['detection', 'recognition', 'timeseries', 'e2e'];
  readonly taskNames: Record<DatasetTask, string> = {
    detection: '검출', recognition: '인식', timeseries: '시계열', e2e: 'E2E 평가',
  };
  readonly steps = ['데이터 종류 정하기', '폴더 준비하기', '등록 정보 입력하기', '폴더 올리기', '검사 결과 확인하기'];

  step = signal(this.data?.step ?? 0);
  task = signal<DatasetTask>(this.data?.task ?? 'detection');

  go(i: number) {
    if (i >= 0 && i < this.steps.length) this.step.set(i);
  }

  /** 1단계에서 종류를 고르면 2단계(폴더 준비)로 넘어감 */
  pickTask(t: DatasetTask) {
    this.task.set(t);
    this.step.set(1);
  }
}
