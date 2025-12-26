import { NgModule, provideBrowserGlobalErrorListeners } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { AppRoutingModule } from './app-routing-module';
import { App } from './app';
import { provideHttpClient, withInterceptors, withInterceptorsFromDi } from '@angular/common/http';
import { MaterialModule } from '../../modules/shared/material-module';
import { MlopsModule } from './../../modules/mlops/mlops-module';
import { apiInterceptor } from './../../modules/mlops/interceptors/api.interceptor';

@NgModule({
  declarations: [
    App,
  ],
  imports: [
    BrowserModule,
    AppRoutingModule,
    MaterialModule,
    MlopsModule,
  ],
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(withInterceptorsFromDi()),
    provideHttpClient(withInterceptors([apiInterceptor]))
  ],
  bootstrap: [App]
})
export class AppModule { }
