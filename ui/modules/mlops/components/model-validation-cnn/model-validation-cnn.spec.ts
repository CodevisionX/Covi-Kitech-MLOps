import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ModelValidationCnn } from './model-validation-cnn';

describe('ModelValidationCnn', () => {
  let component: ModelValidationCnn;
  let fixture: ComponentFixture<ModelValidationCnn>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ModelValidationCnn]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ModelValidationCnn);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
