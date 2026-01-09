import { ChangeDetectorRef, Component, inject, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { CdkTree } from '@angular/cdk/tree';
import { Observable, of, map, tap, catchError, takeUntil, Subject, BehaviorSubject } from 'rxjs';
import { Model } from '../../services/model';
import { Artifact } from '../../services/apis/artifact';
import { Notification } from '../../services/notification';

interface MinioNode {
  name: string;
  type: 'bucket' | 'folder' | 'file';
  bucket: string;
  fullPath: string;
  level: number;
  children$?: BehaviorSubject<MinioNode[]>;
  isLoading?: boolean;
}

@Component({
  selector: 'app-dataset',
  standalone: false,
  templateUrl: './dataset.html',
  styleUrl: './dataset.scss',
})
export class Dataset implements OnInit, OnDestroy {

  @ViewChild(CdkTree) tree!: CdkTree<MinioNode>;

  // 데이터 소스를 단순 배열로 관리해도 최신 CDK Tree는 잘 작동합니다.
  dataSource = new BehaviorSubject<MinioNode[]>([]);
  selectedNode: MinioNode | null = null;

  private readonly artifact = inject(Artifact);
  protected readonly modelService = inject(Model);
  private readonly notificationService = inject(Notification);
  private readonly cdr = inject(ChangeDetectorRef);
  private destroy$ = new Subject<void>();

  ngOnInit() {
    this.loadBuckets();
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadBuckets() {
    this.artifact.getBuckets()
      .pipe(takeUntil(this.destroy$))
      .subscribe(res => {
        const initialData: MinioNode[] = res.datasets.map(name => ({
          name,
          type: 'bucket' as const,
          bucket: name,
          fullPath: '',
          level: 0,
          children$: new BehaviorSubject<MinioNode[]>([]) 
        }));
        this.dataSource.next(initialData);
      });
  }

  childrenAccessor = (node: MinioNode): Observable<MinioNode[]> => {
    if (!node.children$) {
      node.children$ = new BehaviorSubject<MinioNode[]>([]);
    }
    return node.children$.asObservable();
  };

  async onNodeClick(node: MinioNode) {
    // 1. 학습 가능 레벨(2) 체크 및 Signal 업데이트 (기존 로직)
    if (node.level === 2) {
      const fullPath = `${node.bucket}/${node.fullPath}`;
      this.modelService.updatePath(fullPath);
      this.notificationService.showInfo(`📁 데이터셋 선정: ${fullPath}`);
    }

    // 2. 파일이 아니고 자식이 아직 로드되지 않았다면 API 호출
    if (node.type !== 'file' && (!node.children$ || node.children$.value.length === 0)) {
       await this.fetchChildren(node);
    }

    // 3. 트리 토글
    if (this.hasChild(0, node)) {
      this.tree.toggle(node);
    }
  }

  private fetchChildren(node: MinioNode): Promise<void> {
    return new Promise((resolve) => {
      // 이미 로딩 중이면 중복 호출 방지
      if (node.isLoading) return resolve();

      node.isLoading = true;
      console.log(`Fetching data for: ${node.bucket}/${node.fullPath}`);

      this.artifact.getContents(node.bucket, node.fullPath).pipe(
        takeUntil(this.destroy$),
        map(res => {
          const folders = (res.folders || []).map((f: any) => ({
            name: f.split('/').filter(Boolean).pop() + '/',
            type: 'folder' as const, 
            bucket: node.bucket, 
            fullPath: f, 
            level: node.level + 1,
            children$: new BehaviorSubject<MinioNode[]>([])
          }));
          const files = (res.files || []).map((f: any) => ({
            name: f.name, 
            type: 'file' as const, 
            bucket: node.bucket, 
            fullPath: f.full_path, 
            level: node.level + 1
          }));
          return [...folders, ...files];
        }),
        catchError((err) => {
          console.error('API Error:', err);
          return of([]);
        })
      ).subscribe(all => {
        node.isLoading = false;
        if (node.children$) {
            node.children$.next(all);
        }
        resolve();
      });
    });
  }
  
  hasChild = (_: number, node: MinioNode) => node.type !== 'file';
  trackByFn = (index: number, node: MinioNode) => node.bucket + node.fullPath;
}