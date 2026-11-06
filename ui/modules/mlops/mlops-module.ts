import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BaseChartDirective } from 'ng2-charts';
import { Dataset } from './components/dataset/dataset';
import { Deploy } from './components/deploy/deploy';
import { TerminalLog } from './components/dialogs/terminal-log/terminal-log';
import { ModelDetail } from './components/model-detail/model-detail';
import { ModelList } from './components/model-list/model-list';
import { MlopsRoutingModule } from './mlops-routing-module';
import { Dashboard } from './pages/dashboard/dashboard';
import { Train } from './components/train/train';
import { SharedModule } from '../shared/shared-module';
import { ModelValidation } from './components/model-validation/model-validation';
import { ModelDetailCnn } from './components/model-detail-cnn/model-detail-cnn';
import { ModelValidationCnn } from './components/model-validation-cnn/model-validation-cnn';
import { DatasetsPage } from './pages/datasets/datasets';
import { EvalSteps } from './components/eval-steps/eval-steps';
import { EvaluationList } from './pages/evaluations/evaluations';
import { EvaluationDetail } from './pages/evaluation-detail/evaluation-detail';
import { ModelValidationPyfunc } from './components/model-validation-pyfunc/model-validation-pyfunc';
import { ModelDetailV2 } from './components/model-detail-v2/model-detail-v2';
import { RunDetailView } from './components/run-detail-view/run-detail-view';
import { ImportModelDialog } from './components/dialogs/import-model/import-model';
import { SlotViewDialog } from './components/dialogs/slot-view/slot-view';
import { ImageViewerDialog } from './components/dialogs/image-viewer/image-viewer';
import { TrainingStatusDialog } from './components/dialogs/training-status/training-status';
import { TrainingCharts } from './components/training-charts/training-charts';
import { DatasetGuideDialog } from './components/dialogs/dataset-guide/dataset-guide';

@NgModule({
  declarations: [
    Dataset,
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
export class MlopsModule { }
