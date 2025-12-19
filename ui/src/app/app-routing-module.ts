import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { Dataset } from './components/dataset/dataset';
import { ModelList } from './components/model-list/model-list';
import { Train } from './components/train/train';

const routes: Routes = [
  { path: '', redirectTo: 'dataset', pathMatch: 'full' }, // 기본 페이지를 데이터셋으로
  { path: 'dataset', component: Dataset },
  { path: 'train', component: Train },
  { path: 'model-list', component: ModelList },
  { path: '**', redirectTo: 'dataset' } // 잘못된 주소면 데이터셋으로
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
