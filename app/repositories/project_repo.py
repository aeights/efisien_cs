from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        client_id: int,
        *,
        name: str,
        type: str,
        progress: int = 0,
        status: str = "in_progress",
        details: dict | None = None,
    ) -> Project:
        project = Project(
            client_id=client_id,
            name=name,
            type=type,
            progress=progress,
            status=status,
            details=details,
        )
        self.session.add(project)
        self.session.flush()
        return project

    def list_for_user(self, user_id: int) -> list[Project]:
        return list(
            self.session.scalars(
                select(Project).where(Project.client_id == user_id).order_by(Project.id)
            )
        )
