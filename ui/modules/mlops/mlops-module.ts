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

@NgModule({
  declarations: [
    Dataset,
    Train,
    ModelList,
    Dashboard,
    TerminalLog,
    Deploy,
    ModelDetail,
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
