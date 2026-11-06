import { Component, input, output } from '@angular/core';

@Component({
  selector: 'app-breadcrumb',
  standalone: false,
  templateUrl: './breadcrumb.html',
  styleUrl: './breadcrumb.scss',
})
export class Breadcrumb {
  parent = input.required<string>();
  current = input.required<string>();
  parentClick = output<void>();
}
