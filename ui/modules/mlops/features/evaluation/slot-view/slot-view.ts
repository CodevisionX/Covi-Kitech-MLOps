import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { MAT_DIALOG_DATA } from '@angular/material/dialog';
import { EvaluationApi } from '../../../services/apis/evaluation';
import { IEvaluationRow } from '../../../services/apis/models/evaluation.model';

export interface SlotViewData {
  evaluationId: number;
  /** 현재 필터가 적용된 슬롯 목록 (이전/다음 이동용) */
  rows: IEvaluationRow[];
  index: number;
}

const RESULT_LABELS: Record<string, string> = {
  correct: '정답', wrong: '틀림', panel_not_6: '박스 6개 아님', unlabeled: '정답 없음',
};

/** E2E 평가 슬롯 하나를 이미지로 확인합니다: 패널 이미지(검출 박스) + 인식 모델에 들어간 슬롯 이미지 */
@Component({
  selector: 'app-slot-view-dialog',
  standalone: false,
  templateUrl: './slot-view.html',
  styleUrl: './slot-view.scss',
})
export class SlotViewDialog {
  private readonly api = inject(EvaluationApi);
  readonly data = inject<SlotViewData>(MAT_DIALOG_DATA);

  index = signal(this.data.index);
  row = computed(() => this.data.rows[this.index()]);
  panelLoaded = signal(false);
  panelError = signal(false);
  cropError = signal(false);

  panelUrl = computed(() => this.api.panelImageUrl(this.data.evaluationId, this.row()));
  cropUrl = computed(() => {
    const r = this.row();
    return r.slot && r.result !== 'panel_not_6' ? this.api.slotCropUrl(this.data.evaluationId, r) : null;
  });

  resultLabel(r: string): string {
    return RESULT_LABELS[r] || r;
  }

  move(step: number) {
    const next = this.index() + step;
    if (next < 0 || next >= this.data.rows.length) return;
    this.index.set(next);
    this.panelLoaded.set(false);
    this.panelError.set(false);
    this.cropError.set(false);
  }

  @HostListener('document:keydown', ['$event'])
  onKey(e: KeyboardEvent) {
    if (e.key === 'ArrowLeft') this.move(-1);
    if (e.key === 'ArrowRight') this.move(1);
  }
}
