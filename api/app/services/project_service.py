from sqlalchemy.orm import Session
from app.models.project import Project
from app.schemas.project import ProjectCreate

class ProjectService:
    def __init__(self, db: Session):
        self.db = db

    def create_project(self, project_in: ProjectCreate):
        # 중복 이름 체크
        existing = self.db.query(Project).filter(Project.name == project_in.name).first()
        if existing:
            return existing # 혹은 에러 발생
            
        project = Project(
            name=project_in.name,
            description=project_in.description
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def get_projects(self):
        return self.db.query(Project).order_by(Project.id.desc()).all()

    def get_project_by_id(self, project_id: int):
        return self.db.query(Project).filter(Project.id == project_id).first()