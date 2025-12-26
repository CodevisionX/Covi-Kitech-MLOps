import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';

const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' }, // 기본 페이지를
  { path: 'dashboard', loadChildren: () => import('../../modules/mlops/mlops-module').then(m => m.MlopsModule) },
  { path: '**', redirectTo: 'dashboard' } // 잘못된 주소면
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
