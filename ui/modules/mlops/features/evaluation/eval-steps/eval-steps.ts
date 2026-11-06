import { Component, computed, input } from '@angular/core';
import { IEvaluation } from '../../../services/apis/models/evaluation.model';

interface Step { key: string; label: string; help: string; }

const STEPS: Step[] = [
  { key: 'PENDING', label: '대기', help: '평가 작업을 준비하고 있습니다.' },
  { key: 'DETECTING', label: '검출·크롭', help: '패널에서 숫자 묶음을 찾고 슬롯 6개를 잘라 냅니다.' },
  { key: 'RECOGNIZING', label: '인식·평가', help: '잘라 낸 슬롯의 숫자를 읽고 정답과 비교합니다.' },
  { key: 'FINISHED', label: '완료', help: '평가를 마쳤습니다.' },
];

/** E2E 평가 진행 단계 표시 (추론 테스트 화면의 단계 표시와 같은 모양) */
@Component({
  selector: 'app-eval-steps',
  standalone: false,
  templateUrl: './eval-steps.html',
  styleUrl: './eval-steps.scss',
})
export class EvalSteps {
  evaluation = input.required<IEvaluation>();
  /** 표 안에 넣는 작은 모양 */
  compact = input(false);

  readonly steps = STEPS;

  /** 지금 단계 (실패면 멈춘 단계) */
  current = computed(() => {
    const ev = this.evaluation();
    if (ev.status !== 'FAILED') return Math.max(0, STEPS.findIndex(s => s.key === ev.status));
    const msg = `${ev.status_message ?? ''}`;
    if (msg.includes('검출') || msg.includes('detect')) return 1;
    if (msg.includes('인식') || msg.includes('recognize') || msg.includes('보고')) return 2;
    return 0;
  });

  failed = computed(() => this.evaluation().status === 'FAILED');
  finished = computed(() => this.evaluation().status === 'FINISHED');

  state(i: number): 'done' | 'active' | 'failed' | 'todo' {
    if (this.finished() || i < this.current()) return 'done';
    if (i === this.current()) return this.failed() ? 'failed' : 'active';
    return 'todo';
  }

  /** 아래 안내 문구 */
  message = computed(() => {
    const ev = this.evaluation();
    if (this.failed()) return ev.error_message || ev.status_message || '평가가 실패했습니다.';
    if (this.finished()) return '평가를 마쳤습니다. 우측 상단 "현장 배포 패키지 받기"로 운영 PC에 배포할 zip파일을 받을 수 있습니다.';
    return STEPS[this.current()].help;
  });
}
