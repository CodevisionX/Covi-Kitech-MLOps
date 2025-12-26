import { Component, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { TerminalLog } from '../dialogs/terminal-log/terminal-log';
import { Notification } from '../../services/notification';

@Component({
  selector: 'app-deploy',
  standalone: false,
  templateUrl: './deploy.html',
  styleUrl: './deploy.scss',
})
export class Deploy implements OnInit, OnDestroy {

  ngOnInit() {
  }

  ngOnDestroy(): void {

  }

}
