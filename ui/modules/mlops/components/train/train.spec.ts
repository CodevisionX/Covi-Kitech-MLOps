import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Train } from './train';

describe('Train', () => {
  let component: Train;
  let fixture: ComponentFixture<Train>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [Train]
    })
    .compileComponents();

    fixture = TestBed.createComponent(Train);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
