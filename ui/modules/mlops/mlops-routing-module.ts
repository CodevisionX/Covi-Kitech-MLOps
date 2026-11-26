import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { ModelList } from './features/training/model-list/model-list';
import { Dashboard } from './features/training/dashboard/dashboard';
import { Deploy } from './features/inference/deploy/deploy';
import { ModelDetail } from './features/training/model-detail/model-detail';
import { ModelValidation } from './features/inference/model-validation/model-validation';
import { ModelDetailCnn } from './features/training/model-detail-cnn/model-detail-cnn';
import { ModelValidationCnn } from './features/inference/model-validation-cnn/model-validation-cnn';
import { DatasetsPage } from './features/datasets/datasets-page/datasets';
import { EvaluationList } from './features/evaluation/evaluations/evaluations';
import { EvaluationDetail } from './features/evaluation/evaluation-detail/evaluation-detail';
import { ModelValidationPyfunc } from './features/inference/model-validation-pyfunc/model-validation-pyfunc';
import { ModelDetailV2 } from './features/training/model-detail-v2/model-detail-v2';

const routes: Routes = [
  { path: '', redirectTo: 'datasets', pathMatch: 'full' }, // 작업 첫 단계인 데이터셋으로
  { path: 'train', component: Dashboard },
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
  { path: '**', redirectTo: 'datasets' } // 잘못된 주소면
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule]
})
export class MlopsRoutingModule { }
