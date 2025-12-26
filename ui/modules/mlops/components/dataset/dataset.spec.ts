import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Dataset } from './dataset';

describe('Dataset', () => {
  let component: Dataset;
  let fixture: ComponentFixture<Dataset>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [Dataset]
    })
    .compileComponents();

    fixture = TestBed.createComponent(Dataset);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
