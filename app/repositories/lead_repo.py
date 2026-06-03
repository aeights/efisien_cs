from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lead import Lead


class LeadRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_latest(self, user_id: int) -> Lead | None:
        return self.session.scalar(
            select(Lead).where(Lead.user_id == user_id).order_by(Lead.id.desc())
        )

    def get_open(self, user_id: int) -> Lead | None:
        return self.session.scalar(
            select(Lead)
            .where(Lead.user_id == user_id, Lead.status == "new")
            .order_by(Lead.id.desc())
        )

    def upsert(
        self,
        user_id: int,
        *,
        project_type: str | None = None,
        platform: str | None = None,
        requirements: str | None = None,
        budget: str | None = None,
    ) -> Lead:
        lead = self.get_open(user_id)
        if lead is None:
            lead = Lead(user_id=user_id, status="new")
            self.session.add(lead)

        if project_type is not None:
            lead.project_type = project_type
        if platform is not None:
            lead.platform = platform
        if requirements is not None:
            lead.requirements = {"text": requirements}
        if budget is not None:
            lead.budget = budget

        self.session.flush()
        return lead
