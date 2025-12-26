import { Component, inject } from '@angular/core';
import { Layout } from '../../modules/shared/services/layout';

@Component({
  selector: 'app-root',
  templateUrl: './app.html',
  standalone: false,
  styleUrl: './app.scss'
})
export class App {
  
  protected readonly layoutService = inject(Layout);

}
