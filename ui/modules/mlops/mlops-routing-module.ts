import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { ModelList } from './components/model-list/model-list';
import { Dashboard } from '../../modules/mlops/pages/dashboard/dashboard';
import { Deploy } from './components/deploy/deploy';
import { ModelDetail } from './components/model-detail/model-detail';
import { ModelValidation } from './components/model-validation/model-validation';
import { ModelDetailCnn } from './components/model-detail-cnn/model-detail-cnn';
import { ModelValidationCnn } from './components/model-validation-cnn/model-validation-cnn';

const routes: Routes = [
  { path: '', component: Dashboard },
  { path: 'models', component: ModelList },
  { path: 'models/run/yolo/:runId', component: ModelDetail },
  { path: 'models/run/cnn/:runId', component: ModelDetailCnn },
  { path: 'deployments', component: Deploy },
  { path: 'deployments/yolo/:deploymentId', component: ModelValidation },
  { path: 'deployments/cnn/:deploymentId', component: ModelValidationCnn },
  { path: '**', redirectTo: 'dashboard' } // 잘못된 주소면
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule]
})
export class MlopsRoutingModule { }
