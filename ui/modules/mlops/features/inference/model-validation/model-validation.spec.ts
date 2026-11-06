import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ModelValidation } from './model-validation';

describe('ModelValidation', () => {
  let component: ModelValidation;
  let fixture: ComponentFixture<ModelValidation>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ModelValidation]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ModelValidation);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
