from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket


class TicketRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        user_id: int,
        *,
        description: str,
        category: str,
        priority: str,
        project_id: int | None = None,
    ) -> Ticket:
        ticket = Ticket(
            user_id=user_id,
            description=description,
            category=category,
            priority=priority,
            project_id=project_id,
            status="open",
        )
        self.session.add(ticket)
        self.session.flush()
        return ticket

    def get_latest_for_user(self, user_id: int) -> Ticket | None:
        return self.session.scalar(
            select(Ticket).where(Ticket.user_id == user_id).order_by(Ticket.id.desc())
        )

    def assign(self, ticket: Ticket, *, developer: str = "Tim Development") -> Ticket:
        ticket.status = "assigned"
        ticket.assigned_developer = developer
        self.session.flush()
        return ticket
