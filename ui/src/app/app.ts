import { Component, inject, signal } from '@angular/core';
import { Layout } from './core/services/layout';

@Component({
  selector: 'app-root',
  templateUrl: './app.html',
  standalone: false,
  styleUrl: './app.scss'
})
export class App {
  
  protected readonly layoutService = inject(Layout);


}
