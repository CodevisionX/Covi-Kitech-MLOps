import { Component, effect, ElementRef, inject, OnInit, ViewChild } from '@angular/core';
import { MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { TerminalService } from '../../../core/services/terminal';

@Component({
  selector: 'app-terminal-log',
  standalone: false,
  templateUrl: './terminal-log.html',
  styleUrl: './terminal-log.scss',
})
export class TerminalLog implements OnInit {

  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  protected terminalService = inject(TerminalService);
  protected dialogRef = inject(MatDialogRef<TerminalLog>);
  protected data = inject<{ containerId: string }>(MAT_DIALOG_DATA);

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
    if (this.data.containerId) {
      this.terminalService.startStreaming(this.data.containerId);
    }
  }

  private scrollToBottom(): void {
    if (!this.scrollContainer) return;
    requestAnimationFrame(() => {
      const element = this.scrollContainer.nativeElement;
      element.scrollTo({
        top: element.scrollHeight,
        behavior: 'smooth'
      });
    });
  }

  close() {
    this.dialogRef.close();
  }

}

