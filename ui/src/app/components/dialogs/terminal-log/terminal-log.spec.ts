import { ComponentFixture, TestBed } from '@angular/core/testing';

import { TerminalLog } from './terminal-log';

describe('TerminalLog', () => {
  let component: TerminalLog;
  let fixture: ComponentFixture<TerminalLog>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [TerminalLog]
    })
    .compileComponents();

    fixture = TestBed.createComponent(TerminalLog);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
