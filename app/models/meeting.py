from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    meeting_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    meeting_link: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="scheduled", server_default="scheduled")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
