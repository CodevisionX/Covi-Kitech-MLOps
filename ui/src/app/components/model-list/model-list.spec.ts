import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ModelList } from './model-list';

describe('ModelList', () => {
  let component: ModelList;
  let fixture: ComponentFixture<ModelList>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ModelList]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ModelList);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
