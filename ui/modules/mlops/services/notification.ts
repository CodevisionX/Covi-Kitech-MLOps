import { inject, Injectable } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';

@Injectable({
  providedIn: 'root',
})
export class Notification {
  
  private snackBar = inject(MatSnackBar);

  private readonly config = {
    duration: 3000,
    horizontalPosition: 'right' as const,
    verticalPosition: 'top' as const,
  };

  showInfo(message: string) {
    this.snackBar.open(message, '확인', this.config);
  }

  showSuccess(message: string) {
    this.snackBar.open(`✅ ${message}`, '닫기', {
      ...this.config,
      panelClass: ['success-snackbar']
    });
  }

  // ✅ 추가: 경고 알림 (주황색/노란색 계열)
  showWarning(message: string) {
    this.snackBar.open(`⚠️ 주의: ${message}`, '확인', {
      ...this.config,
      panelClass: ['warning-snackbar']
    });
  }

  showError(message: string) {
    this.snackBar.open(`❌ 에러: ${message}`, '닫기', {
      ...this.config,
      duration: 5000,
      panelClass: ['error-snackbar']
    });
  }

  // 기존의 SSE 업데이트 처리 로직 (필요 시 유지)
  processUpdates(updates: any[]) {
    const completed = updates.filter(u => u.status === 'COMPLETED');
    if (completed.length > 0) {
      this.showSuccess(`${completed.length}개의 학습이 완료되었습니다.`);
    }
  }

}
