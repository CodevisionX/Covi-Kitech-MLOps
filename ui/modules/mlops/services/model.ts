import { Injectable, signal } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class Model {
  
  // 학습 가능한 데이터셋 경로를 저장하는 변수
  selectedDatasetPath = signal<string>(''); 

  updatePath(path: string) {
    this.selectedDatasetPath.set(path);
  }

}
