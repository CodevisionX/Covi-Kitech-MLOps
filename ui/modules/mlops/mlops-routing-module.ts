import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { ModelList } from './components/model-list/model-list';
import { Dashboard } from '../../modules/mlops/pages/dashboard/dashboard';
import { Deploy } from './components/deploy/deploy';
import { ModelDetail } from './components/model-detail/model-detail';
import { ModelValidation } from './components/model-validation/model-validation';
import { ModelDetailCnn } from './components/model-detail-cnn/model-detail-cnn';
import { ModelValidationCnn } from './components/model-validation-cnn/model-validation-cnn';
import { DatasetsPage } from './pages/datasets/datasets';
import { EvaluationList } from './pages/evaluations/evaluations';
import { EvaluationDetail } from './pages/evaluation-detail/evaluation-detail';
import { ModelValidationPyfunc } from './components/model-validation-pyfunc/model-validation-pyfunc';
import { ModelDetailV2 } from './components/model-detail-v2/model-detail-v2';

const routes: Routes = [
  { path: '', component: Dashboard },
  { path: 'models', component: ModelList },
  { path: 'models/run/yolo/:runId', component: ModelDetail },
  { path: 'models/run/cnn/:runId', component: ModelDetailCnn },
  { path: 'models/run/v2/:runId', component: ModelDetailV2 },
  { path: 'datasets', component: DatasetsPage },
  { path: 'evaluations', component: EvaluationList },
  { path: 'evaluations/:evaluationId', component: EvaluationDetail },
  { path: 'deployments', component: Deploy },
  { path: 'deployments/yolo/:deploymentId', component: ModelValidation },
  { path: 'deployments/cnn/:deploymentId', component: ModelValidationCnn },
  { path: 'deployments/pyfunc/:deploymentId', component: ModelValidationPyfunc },
  { path: '**', redirectTo: 'dashboard' } // 잘못된 주소면
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule]
})
export class MlopsRoutingModule { }
