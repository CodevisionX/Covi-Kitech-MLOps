import { Component, effect, ElementRef, inject, ViewChild } from '@angular/core';
import { TerminalService } from './../../core/services/terminal';

@Component({
  selector: 'app-terminal',
  standalone: false,
  templateUrl: './terminal.html',
  styleUrl: './terminal.scss',
})
export class Terminal {

  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  protected terminalService = inject(TerminalService);

  constructor() {
    // logs 시그널이 변경될 때마다 실행됩니다.
    effect(() => {
      // logs()를 호출함으로써 종속성을 등록합니다.
      const currentLogs = this.terminalService.logs();

      // 로그가 추가된 후 DOM이 업데이트될 시간을 아주 잠깐 주기 위해 setTimeout을 사용합니다.
      if (currentLogs.length > 0) {
        this.scrollToBottom();
      }
    });
  }
  
  private scrollToBottom(): void {
    if (!this.scrollContainer) return;

    requestAnimationFrame(() => {
      const element = this.scrollContainer.nativeElement;
      element.scrollTo({
        top: element.scrollHeight,
        behavior: 'smooth' // 부드러운 스크롤을 원하시면 추가
      });
    });
  }

}
