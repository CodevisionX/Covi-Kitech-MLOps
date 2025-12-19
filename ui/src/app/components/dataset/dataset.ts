import { Component, inject, OnInit, ViewChild } from '@angular/core';
import { Api } from '../../core/services/api';
import { ArrayDataSource } from '@angular/cdk/collections';
import { CdkTree } from '@angular/cdk/tree';
import { Observable, of, map, tap, catchError } from 'rxjs';

interface MinioNode {
  name: string;
  type: 'bucket' | 'folder' | 'file';
  bucket: string;
  fullPath: string;
  level: number;
  children?: MinioNode[];
  isLoading?: boolean;
}

@Component({
  selector: 'app-dataset',
  standalone: false,
  templateUrl: './dataset.html',
  styleUrl: './dataset.scss',
})
export class Dataset implements OnInit {
  @ViewChild(CdkTree) tree!: CdkTree<MinioNode>;

  // [변경] 데이터 소스를 단순 배열로 관리해도 최신 CDK Tree는 잘 작동합니다.
  dataSource = new ArrayDataSource<MinioNode>([]);
  selectedNode: MinioNode | null = null;

  private readonly apiService = inject(Api);

  ngOnInit() {
    this.loadBuckets();
  }

  loadBuckets() {
    this.apiService.getBuckets().subscribe(res => {
      const buckets: MinioNode[] = res.datasets.map(name => ({
        name,
        type: 'bucket',
        bucket: name,
        fullPath: '',
        level: 0,
        children: undefined // undefined로 두어 로드 전임을 표시
      }));
      this.dataSource = new ArrayDataSource(buckets);
    });
  }

  /** * [지연 로딩의 정석] 
   * 트리는 자식 노드가 필요할 때 이 함수를 호출합니다.
   */
  childrenAccessor = (node: MinioNode): Observable<MinioNode[]> => {
    if (node.type === 'file') return of([]);

    // 1. 이미 데이터를 불러왔다면 캐시된 데이터 반환
    if (node.children) return of(node.children);

    // 2. 데이터가 없다면 서버에서 가져오기 (이때 Observable을 반환하면 트리가 기다립니다)
    node.isLoading = true;
    return this.apiService.getContents(node.bucket, node.fullPath).pipe(
      map(res => {
        const folders = res.folders.map((f: any) => ({
          name: f.split('/').filter(Boolean).pop() + '/',
          type: 'folder', bucket: node.bucket, fullPath: f, level: node.level + 1
        }));
        const files = res.files.map((f: any) => ({
          name: f.name, type: 'file', bucket: node.bucket, fullPath: f.full_path, level: node.level + 1
        }));
        
        const all = [...folders, ...files];
        node.children = all; // 데이터 저장(캐싱)
        return all;
      }),
      tap(() => node.isLoading = false),
      catchError(() => {
        node.isLoading = false;
        return of([]);
      })
    );
  };

  onNodeClick(node: MinioNode) {
    this.selectedNode = node;
    if (this.hasChild(0, node)) {
      this.tree.toggle(node);
    }
  }

  hasChild = (_: number, node: MinioNode) => node.type !== 'file';
}