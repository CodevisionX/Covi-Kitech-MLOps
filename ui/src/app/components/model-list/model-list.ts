import { Component, inject, OnInit } from '@angular/core';
import { Api } from '../../core/services/api';

@Component({
  selector: 'app-model-list',
  standalone: false,
  templateUrl: './model-list.html',
  styleUrl: './model-list.scss',
})
export class ModelList implements OnInit {

  protected models: any[] = [];
  protected displayedColumns: string[] = ['name', 'version', 'status', 'link'];

  private readonly apiService = inject(Api);

  ngOnInit(): void {
    this.apiService.getModels().subscribe(data => this.models = data);
  }

  goToMlflow(runId: string) {
    // MLflow 서버 주소로 새 창 열기 (특정 실험 run_id로 바로 이동)
    const mlflowUrl = `http://localhost:5000/#/experiments/0/runs/${runId}`;
    window.open(mlflowUrl, '_blank');
  }

}
