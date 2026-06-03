from datetime import datetime

from app.integrations.calendar import WIB
from app.models.user import User
from app.repositories.lead_repo import LeadRepository
from app.repositories.meeting_repo import MeetingRepository


def _user_with_lead(session, phone="0812"):
    u = User(name="Budi", phone=phone)
    session.add(u)
    session.flush()
    lead = LeadRepository(session).upsert(u.id, project_type="POS")
    return u, lead


def test_create_and_scheduled_times(session):
    _u, lead = _user_with_lead(session)
    repo = MeetingRepository(session)
    m = repo.create(lead.id, datetime(2099, 1, 5, 9, 0, tzinfo=WIB), "https://meet.efisien.id/x")
    assert m.id is not None
    assert m.status == "scheduled"
    assert len(repo.scheduled_times()) == 1


def test_get_latest_for_user(session):
    u, lead = _user_with_lead(session, phone="0813")
    repo = MeetingRepository(session)
    repo.create(lead.id, datetime(2099, 1, 5, 9, 0, tzinfo=WIB), "l1")
    m2 = repo.create(lead.id, datetime(2099, 1, 6, 9, 0, tzinfo=WIB), "l2")
    assert repo.get_latest_for_user(u.id).id == m2.id
