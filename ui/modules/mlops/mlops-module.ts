import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BaseChartDirective } from 'ng2-charts';
import { Deploy } from './features/inference/deploy/deploy';
import { TerminalLog } from './features/common/terminal-log/terminal-log';
import { ModelDetail } from './features/training/model-detail/model-detail';
import { ModelList } from './features/training/model-list/model-list';
import { MlopsRoutingModule } from './mlops-routing-module';
import { Dashboard } from './features/training/dashboard/dashboard';
import { Train } from './features/training/train/train';
import { SharedModule } from '../shared/shared-module';
import { applyChartTheme } from '../shared/utils/chart-theme';
import { ModelValidation } from './features/inference/model-validation/model-validation';
import { ModelDetailCnn } from './features/training/model-detail-cnn/model-detail-cnn';
import { ModelValidationCnn } from './features/inference/model-validation-cnn/model-validation-cnn';
import { DatasetsPage } from './features/datasets/datasets-page/datasets';
import { EvalSteps } from './features/evaluation/eval-steps/eval-steps';
import { EvaluationList } from './features/evaluation/evaluations/evaluations';
import { EvaluationDetail } from './features/evaluation/evaluation-detail/evaluation-detail';
import { ModelValidationPyfunc } from './features/inference/model-validation-pyfunc/model-validation-pyfunc';
import { ModelDetailV2 } from './features/training/model-detail-v2/model-detail-v2';
import { RunDetailView } from './features/training/run-detail-view/run-detail-view';
import { ImportModelDialog } from './features/training/import-model/import-model';
import { SlotViewDialog } from './features/evaluation/slot-view/slot-view';
import { ImageViewerDialog } from './features/training/image-viewer/image-viewer';
import { TrainingStatusDialog } from './features/training/training-status/training-status';
import { TrainingCharts } from './features/training/training-charts/training-charts';
import { DatasetGuideDialog } from './features/datasets/dataset-guide/dataset-guide';

@NgModule({
  declarations: [
    Train,
    ModelList,
    Dashboard,
    TerminalLog,
    Deploy,
    ModelDetail,
    ModelValidation,
    ModelDetailCnn,
    ModelValidationCnn,
    DatasetsPage,
    EvalSteps,
    EvaluationList,
    EvaluationDetail,
    ModelValidationPyfunc,
    ModelDetailV2,
    RunDetailView,
    ImportModelDialog,
    SlotViewDialog,
    ImageViewerDialog,
    TrainingStatusDialog,
    TrainingCharts,
    DatasetGuideDialog,
  ],
  imports: [
    CommonModule,
    SharedModule,
    MlopsRoutingModule,
    BaseChartDirective,
  ],
  exports: [

  ]
})
export class MlopsModule {
  constructor() {
    applyChartTheme();
  }
}
