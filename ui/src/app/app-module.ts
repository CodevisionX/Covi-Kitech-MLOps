import { NgModule, provideBrowserGlobalErrorListeners } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { AppRoutingModule } from './app-routing-module';
import { App } from './app';
import { Dataset } from './components/dataset/dataset';
import { Train } from './components/train/train';
import { ModelList } from './components/model-list/model-list';
import { provideHttpClient, withInterceptorsFromDi } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { MaterialModule } from './material-module';
import { Dashboard } from './components/dashboard/dashboard';
import { TerminalLog } from './components/dialogs/terminal-log/terminal-log';
import { Deploy } from './components/deploy/deploy';
import { BaseChartDirective } from 'ng2-charts';
import { ModelDetail } from './components/model-detail/model-detail';

@NgModule({
  declarations: [
    App,
    Dataset,
    Train,
    ModelList,
    Dashboard,
    TerminalLog,
    Deploy,
    ModelDetail,
  ],
  imports: [
    BrowserModule,
    AppRoutingModule,
    FormsModule,
    MaterialModule,
    BaseChartDirective,
  ],
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(withInterceptorsFromDi())
  ],
  bootstrap: [App]
})
export class AppModule { }
