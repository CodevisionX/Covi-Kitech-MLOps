import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ModelDetail } from './model-detail';

describe('ModelDetail', () => {
  let component: ModelDetail;
  let fixture: ComponentFixture<ModelDetail>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ModelDetail]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ModelDetail);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
