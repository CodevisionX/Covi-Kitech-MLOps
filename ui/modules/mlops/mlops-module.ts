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
