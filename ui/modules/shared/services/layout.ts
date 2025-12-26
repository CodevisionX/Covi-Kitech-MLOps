import { Injectable } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class Layout {
  
  private bodyHeight: number = 0;
  
  public getBodyHeight() {
    this.bodyHeight = window.innerHeight - 64;
    return  `${this.bodyHeight}px`;
  }
  
}
