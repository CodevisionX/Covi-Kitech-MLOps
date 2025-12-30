import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable, catchError } from 'rxjs';
import { BaseApi } from './baseApi';
import { IProject, IProjectCreate } from './models/project.model';

@Injectable({
  providedIn: 'root',
})
export class Project extends BaseApi {

  private http = inject(HttpClient);

  getProjects(): Observable<IProject[]> {
    return this.http.get<IProject[]>('/projects')
      .pipe(catchError(this.handleError));
  }

  createProject(projectData: IProjectCreate): Observable<IProject> {
    return this.http.post<IProject>('/projects', projectData)
      .pipe(catchError(this.handleError));
  }

  getProject(projectId: number): Observable<IProject> {
    return this.http.get<IProject>(`/projects/${projectId}`)
      .pipe(catchError(this.handleError));
  }
  
}