from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message


class MessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        user_id: int,
        role: str,
        content: str,
        tool_name: str | None = None,
    ) -> Message:
        message = Message(
            user_id=user_id, role=role, content=content, tool_name=tool_name
        )
        self.session.add(message)
        self.session.flush()
        return message

    def recent(self, user_id: int, limit: int = 15) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        rows = list(self.session.scalars(stmt))
        return list(reversed(rows))
