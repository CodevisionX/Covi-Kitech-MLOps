import { Component, input, output } from '@angular/core';

@Component({
  selector: 'app-page-header',
  standalone: false,
  templateUrl: './page-header.html',
  styleUrl: './page-header.scss',
})
export class PageHeader {
  heading = input.required<string>();
  subtitle = input<string>();
  showBack = input(false);
  back = output<void>();
}
