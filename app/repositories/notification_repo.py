from sqlalchemy.orm import Session

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, target_role: str, *, reason: str, payload: dict | None = None) -> Notification:
        notif = Notification(
            target_role=target_role, reason=reason, payload=payload, status="sent"
        )
        self.session.add(notif)
        self.session.flush()
        return notif
