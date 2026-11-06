import { Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { TerminalLog } from '../dialogs/terminal-log/terminal-log';
import { Notification } from '../../services/notification';
import { Deployment } from '../../services/apis/deployment';
import { DeploymentStatus, IDeployment } from '../../services/apis/models/deployment.model';
import { Subscription } from 'rxjs';
import { Router } from '@angular/router';
import { MODEL_CONFIGS } from '../../configs/model-config';

@Component({
  selector: 'app-deploy',
  standalone: false,
  templateUrl: './deploy.html',
  styleUrl: './deploy.scss',
})
export class Deploy implements OnInit, OnDestroy {

  private readonly deploymentService = inject(Deployment);
  private readonly notificationService = inject(Notification);
  private readonly dialog = inject(MatDialog);
  private readonly router = inject(Router);

  activeDeployments = signal<IDeployment[]>([]);
  private statusSub: Subscription | null = null;
  isLoading = signal<boolean>(false);

  private readonly dummyRows = new Array(3).fill({});
  displayDeployments = computed(() =>
    this.isLoading() ? this.dummyRows : this.activeDeployments()
  );

  private readonly deployWorkflow = [
    DeploymentStatus.PENDING,
    DeploymentStatus.REGISTERING,
    DeploymentStatus.BUILDING,
    DeploymentStatus.CREATING,
    DeploymentStatus.RUNNING
  ];

  ngOnInit() {
    this.loadActiveDeployments();
    this.initStatusSubscription();
  }

  // 1. 활성 배포 목록 로드
  loadActiveDeployments() {
    this.isLoading.set(true);
    this.deploymentService.getActiveDeployments().subscribe({
      next: (list) => {
        this.activeDeployments.set(list);
        this.isLoading.set(false);
      },
      error: () => {
        this.notificationService.showError('추론 서버 목록을 가져오지 못했습니다.');
        this.isLoading.set(false);
      }
    });
  }

  // 2. SSE를 통한 실시간 상태 업데이트 구독
  initStatusSubscription() {
    this.statusSub = this.deploymentService.getDeploymentUpdates().subscribe({
      next: (payload) => {
        if (payload.event === 'deployment_status') {
          this.syncDeploymentStatus(payload.data);
        }
      }
    });
  }

  private syncDeploymentStatus(data: any) {
    this.activeDeployments.update(list => {
      // 1. 삭제되었거나, 사용자가 중단/취소한 경우 목록에서 즉시 제거
      if (data.status === 'DELETED' || data.status === 'STOPPED' || data.status === 'CANCELED') {
        return list.filter(d => d.id !== data.deployment_id);
      }

      const target = list.find(d => d.id === data.deployment_id);
      if (target) {
        // 2. 진행 중 상태 업데이트
        return list.map(d => d.id === data.deployment_id 
          ? { 
              ...d, 
              ...data,
              status: data.status,
              status_message: data.message || d.status_message
            } 
          : d
        );
      } else {
        // 3. 신규 배포 건이면 목록 새로고침
        this.loadActiveDeployments();
        return list;
      }
    });

    // 성공적으로 RUNNING이 되었을 때 알림
    if (data.status === DeploymentStatus.RUNNING) {
      this.notificationService.showSuccess(`추론 서버가 준비되었습니다.`);
    }
  }

  // 3. 추론 서버 중지
  onStop(id: number) {
    if (confirm('추론 서버를 중지할까요? 컨테이너와 포트가 바로 반납됩니다.')) {
      this.deploymentService.stopDeployment(id).subscribe({
        next: () => {
          this.notificationService.showSuccess('추론 서버를 중지했습니다.');
          this.loadActiveDeployments();
        }
      });
    }
  }

  onDelete(id: number) {
    if (!confirm('이 추론 서버 기록을 삭제하시겠습니까? 실행 중인 컨테이너도 함께 제거됩니다.')) return;

    this.deploymentService.deleteDeployment(id).subscribe({
      next: () => {
        this.notificationService.showSuccess('추론 서버 기록을 삭제했습니다.');
        // SSE가 'DELETED' 이벤트를 보내주면 자동으로 리스트에서 필터링됩니다.
      },
      error: (err) => {
        this.notificationService.showError('삭제 중 오류가 발생했습니다.');
      }
    });
  }

  // 4. 로그 스트리밍 창 열기 (제공된 getDeploymentLogStream 활용)
  viewLogs(dep: IDeployment) {
    const terminalLog = this.dialog.open(TerminalLog, {
      width: '900px',
      height: '650px',
      panelClass: 'custom-terminal-dialog',
      data: {
        id: dep.id,
        title: `${dep.model_name} (ID: ${dep.id}) 실시간 로그`,
        type: 'deployment',
        status: dep.status
      }
    });
  }

  isStepCompleted(currentStatus: DeploymentStatus, step: string): boolean {
    if (currentStatus === DeploymentStatus.RUNNING) return true;
    if (currentStatus === DeploymentStatus.FAILED) return false;

    const currentIndex = this.deployWorkflow.indexOf(currentStatus);
    const stepIndex = this.deployWorkflow.indexOf(step as DeploymentStatus);
    return currentIndex > stepIndex;
  }

  isStepActive(currentStatus: DeploymentStatus, step: string): boolean {
    return currentStatus === step;
  }

  getStepLabel(step: string): string {
    const labels: any = {
      'REGISTERING': '모델 등록', 'BUILDING': '이미지 빌드',
      'CREATING': '컨테이너 생성', 'RUNNING': '실행 중'
    };
    return labels[step] || step;
  }

  /** 서버가 기록한 localhost 를 지금 화면에 접속한 주소로 바꿔, 이 브라우저의 PC에서 바로 쓸 수 있게 함 */
  apiUrl(url: string): string {
    try {
      const u = new URL(url);
      if (u.hostname === 'localhost' || u.hostname === '127.0.0.1') u.hostname = location.hostname;
      return u.toString();
    } catch {
      return url;
    }
  }

  copyUrl(url: string) {
    const done = () => this.notificationService.showInfo('API 주소를 복사했습니다.');
    // http 로 다른 PC에서 접속하면 navigator.clipboard 를 쓸 수 없어 예전 방식으로 복사
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(url).then(done, () => this.copyFallback(url, done));
    } else {
      this.copyFallback(url, done);
    }
  }

  private copyFallback(url: string, done: () => void) {
    const ta = document.createElement('textarea');
    ta.value = url;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    if (ok) done(); else this.notificationService.showError('복사하지 못했습니다. 주소를 직접 선택해 복사해 주세요.');
  }

  /** MLflow 서빙 배포 (v1 방식 기존 기록은 model_family 가 'yolo' / 'cnn' 이라 BentoML 경로) */
  isPyfunc(dep: IDeployment): boolean {
    return !!dep.model_family && !!MODEL_CONFIGS[dep.model_family]?.pyfunc;
  }

  /** MLflow 서빙은 빌드 단계가 없습니다 */
  stepsFor(dep: IDeployment): string[] {
    return this.isPyfunc(dep) ? ['REGISTERING', 'CREATING', 'RUNNING'] : ['REGISTERING', 'BUILDING', 'CREATING', 'RUNNING'];
  }

  onNavigateToValidation(dep: IDeployment) {
    if (!dep || !dep.id || !dep.model_name) return;

    if (this.isPyfunc(dep)) {
      this.router.navigate(['/dashboard', 'deployments', 'pyfunc', dep.id]);
      return;
    }
    const family = dep.model_family || (dep.model_name.toLowerCase().includes('yolo') ? 'yolo' : 'cnn');
    this.router.navigate(['/dashboard', 'deployments', family === 'yolo' ? 'yolo' : 'cnn', dep.id]);
  }

  ngOnDestroy() {
    if (this.statusSub) {
      this.statusSub.unsubscribe();
    }
  }

}
