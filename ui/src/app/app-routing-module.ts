import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { ModelList } from './components/model-list/model-list';
import { Dashboard } from './components/dashboard/dashboard';
import { Deploy } from './components/deploy/deploy';
import { ModelDetail } from './components/model-detail/model-detail';

const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' }, // 기본 페이지를
  { path: 'dashboard', component: Dashboard },
  { path: 'models', component: ModelList },
  { path: 'models/run/:runId', component: ModelDetail },
  { path: 'deployments', component: Deploy },
  { path: '**', redirectTo: 'dashboard' } // 잘못된 주소면
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
