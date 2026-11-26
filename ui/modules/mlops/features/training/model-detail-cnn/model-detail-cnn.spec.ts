import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ModelDetailCnn } from './model-detail-cnn';

describe('ModelDetailCnn', () => {
  let component: ModelDetailCnn;
  let fixture: ComponentFixture<ModelDetailCnn>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ModelDetailCnn]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ModelDetailCnn);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
