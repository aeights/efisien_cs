from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_type: Mapped[str | None] = mapped_column(String(120))
    platform: Mapped[str | None] = mapped_column(String(120))
    requirements: Mapped[dict | None] = mapped_column(JSON)  # {"text": "..."}
    budget: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="new", server_default="new")
    proposal: Mapped[dict | None] = mapped_column(JSON)  # Sprint 7; NULL for now
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
