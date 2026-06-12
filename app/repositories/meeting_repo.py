from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.meeting import Meeting


class MeetingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def scheduled_times(self) -> set[datetime]:
        rows = self.session.scalars(
            select(Meeting.meeting_time).where(Meeting.status == "scheduled")
        )
        return set(rows)

    def get_latest_for_user(self, user_id: int) -> Meeting | None:
        return self.session.scalar(
            select(Meeting)
            .join(Lead, Meeting.lead_id == Lead.id)
            .where(Lead.user_id == user_id)
            .order_by(Meeting.id.desc())
        )

    def create(self, lead_id: int, meeting_time: datetime, meeting_link: str) -> Meeting:
        meeting = Meeting(
            lead_id=lead_id,
            meeting_time=meeting_time,
            meeting_link=meeting_link,
            status="scheduled",
        )
        self.session.add(meeting)
        self.session.flush()
        return meeting

    def set_google_event_id(self, meeting: Meeting, event_id: str) -> Meeting:
        meeting.google_event_id = event_id
        self.session.flush()
        return meeting
