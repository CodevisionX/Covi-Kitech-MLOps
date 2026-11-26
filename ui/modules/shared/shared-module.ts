import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MaterialModule } from './material-module';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { PageHeader } from './ui/page-header/page-header';
import { Breadcrumb } from './ui/breadcrumb/breadcrumb';



@NgModule({
  declarations: [PageHeader, Breadcrumb],
  imports: [
    CommonModule,
    MaterialModule,
    FormsModule,
    ReactiveFormsModule,
  ],
  exports: [
    PageHeader,
    Breadcrumb,
    MaterialModule,
    FormsModule,
    ReactiveFormsModule,
  ]
})
export class SharedModule { }
