import { Component, effect, ElementRef, inject, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { TerminalService } from '../../../services/terminal';

@Component({
  selector: 'app-terminal-log',
  standalone: false,
  templateUrl: './terminal-log.html',
  styleUrl: './terminal-log.scss',
})
export class TerminalLog implements OnInit, OnDestroy {

  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  protected terminalService = inject(TerminalService);
  protected dialogRef = inject(MatDialogRef<TerminalLog>);
  protected data = inject<{ jobId: number, status: string }>(MAT_DIALOG_DATA);

  constructor() {
    // 로그가 업데이트될 때마다 하단 스크롤
    effect(() => {
      if (this.terminalService.logs().length > 0) {
        this.scrollToBottom();
      }
    });
  }

  ngOnInit() {
    // 다이얼로그가 열리자마자 해당 컨테이너 ID로 스트리밍 시작
    if (this.data.jobId) {
      this.terminalService.startStreaming(this.data.jobId, this.data.status);
    }
  }

  ngOnDestroy(): void {
    this.terminalService.close();
  }

  private scrollToBottom(): void {
    if (!this.scrollContainer) return;

    const element = this.scrollContainer.nativeElement;
    const threshold = 100; // 바닥에서 100px 이내에 있을 때만 자동 스크롤
    const isNearBottom = element.scrollHeight - element.scrollTop - element.clientHeight < threshold;

    if (isNearBottom) {
      requestAnimationFrame(() => {
        try {
          element.scrollTop = element.scrollHeight;
        } catch (e) { }
      });
    }
  }

  close() {
    this.dialogRef.close();
  }

}

