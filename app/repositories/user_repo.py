from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create(
        self,
        *,
        name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
    ) -> User:
        user: User | None = None
        if phone:
            user = self.session.scalar(select(User).where(User.phone == phone))
        if user is None and email:
            user = self.session.scalar(select(User).where(User.email == email))

        if user is None:
            user = User(name=name, phone=phone, email=email)
            self.session.add(user)
            self.session.flush()
            return user

        if name:
            user.name = name
        user.last_seen_at = datetime.now(timezone.utc)
        return user
