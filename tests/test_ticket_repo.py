from app.models.user import User
from app.repositories.ticket_repo import TicketRepository


def _user(session):
    u = User(name="Klien", phone="0851")
    session.add(u)
    session.flush()
    return u


def test_create_ticket_defaults_open(session):
    u = _user(session)
    t = TicketRepository(session).create(
        u.id, description="tidak bisa login", category="bug", priority="high"
    )
    assert t.status == "open"
    assert t.project_id is None
    assert t.category == "bug"
    assert t.assigned_developer is None


def test_get_latest_for_user(session):
    u = _user(session)
    repo = TicketRepository(session)
    repo.create(u.id, description="a", category="question", priority="low")
    repo.create(u.id, description="b", category="bug", priority="high")
    latest = repo.get_latest_for_user(u.id)
    assert latest.description == "b"


def test_assign_sets_status_and_developer(session):
    u = _user(session)
    repo = TicketRepository(session)
    t = repo.create(u.id, description="x", category="bug", priority="med")
    repo.assign(t)
    assert t.status == "assigned"
    assert t.assigned_developer == "Tim Development"
