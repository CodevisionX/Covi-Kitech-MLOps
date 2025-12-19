import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { Dataset } from './components/dataset/dataset';
import { ModelList } from './components/model-list/model-list';
import { Train } from './components/train/train';
import { Dashboard } from './components/dashboard/dashboard';

const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' }, // 기본 페이지를 데이터셋으로
  { path: 'dashboard', component: Dashboard },
  { path: 'train', component: Train },
  { path: 'model-list', component: ModelList },
  { path: '**', redirectTo: 'dashboard' } // 잘못된 주소면 데이터셋으로
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
