import json

from app.agent.tools import TOOL_SPECS, dispatch
from app.llm.base import ToolCall


class _FakeRetriever:
    def __init__(self, hits):
        self._hits = hits

    def search(self, query, k=4):
        return self._hits


def test_tool_specs_include_search():
    assert any(t.name == "search_knowledge_base" for t in TOOL_SPECS)


def test_dispatch_search_returns_results():
    retriever = _FakeRetriever([{"text": "Layanan ERP", "source": "profile.txt", "score": 0.1}])
    out = json.loads(
        dispatch(ToolCall(name="search_knowledge_base", args={"query": "layanan"}), retriever=retriever)
    )
    assert out["results"][0]["source"] == "profile.txt"
    assert out["results"][0]["text"] == "Layanan ERP"


def test_dispatch_empty_hits_reports_no_info():
    out = json.loads(
        dispatch(ToolCall(name="search_knowledge_base", args={"query": "x"}), retriever=_FakeRetriever([]))
    )
    assert "result" in out and "Tidak ada" in out["result"]


def test_dispatch_unknown_tool():
    out = json.loads(dispatch(ToolCall(name="nope", args={}), retriever=_FakeRetriever([])))
    assert "error" in out


def test_dispatch_handles_tool_exception():
    class Boom:
        def search(self, query, k=4):
            raise RuntimeError("boom")

    out = json.loads(
        dispatch(ToolCall(name="search_knowledge_base", args={"query": "x"}), retriever=Boom())
    )
    assert out["error"] == "boom"


from app.models.user import User
from app.repositories.lead_repo import LeadRepository


def _seed_user(session, phone="0812", email=None):
    user = User(name="Budi", phone=phone, email=email)
    session.add(user)
    session.flush()
    return user


def test_dispatch_create_lead_injects_user(session):
    user = _seed_user(session)
    out = json.loads(
        dispatch(
            ToolCall(name="create_lead", args={"project_type": "POS", "requirements": "3 cabang"}),
            retriever=None,
            session=session,
            user=user,
        )
    )
    assert out["project_type"] == "POS"
    assert out["status"] == "new"
    lead = LeadRepository(session).get_latest(user.id)
    assert lead.user_id == user.id
    assert lead.requirements == {"text": "3 cabang"}


def test_dispatch_get_lead_empty(session):
    user = _seed_user(session, phone="0813")
    out = json.loads(
        dispatch(ToolCall(name="get_lead", args={}), retriever=None, session=session, user=user)
    )
    assert "Belum ada" in out["result"]


def test_dispatch_get_lead_returns_latest(session):
    user = _seed_user(session, phone="0814")
    dispatch(
        ToolCall(name="create_lead", args={"project_type": "Website", "budget": "10 juta"}),
        retriever=None,
        session=session,
        user=user,
    )
    out = json.loads(
        dispatch(ToolCall(name="get_lead", args={}), retriever=None, session=session, user=user)
    )
    assert out["project_type"] == "Website"
    assert out["budget"] == "10 juta"


from datetime import datetime

from app.integrations.calendar import WIB, fmt_slot
from app.repositories.meeting_repo import MeetingRepository
from tests.fakes import FakeCalendar, FakeEmail

_SLOT = datetime(2099, 1, 5, 9, 0, tzinfo=WIB)


def test_dispatch_get_available_slots(session):
    user = _seed_user(session, phone="0820")
    out = json.loads(
        dispatch(
            ToolCall(name="get_available_slots", args={}),
            session=session,
            user=user,
            calendar=FakeCalendar([_SLOT]),
        )
    )
    assert out["slots"] == ["2099-01-05 09:00"]


def test_dispatch_create_meeting_requires_lead(session):
    user = _seed_user(session, phone="0821")
    out = json.loads(
        dispatch(
            ToolCall(name="create_meeting", args={"slot": "2099-01-05 09:00"}),
            session=session,
            user=user,
            calendar=FakeCalendar([_SLOT]),
        )
    )
    assert "result" in out and "lead" in out["result"].lower()


def test_dispatch_create_meeting_books_slot(session):
    user = _seed_user(session, phone="0822")
    LeadRepository(session).upsert(user.id, project_type="POS")
    out = json.loads(
        dispatch(
            ToolCall(name="create_meeting", args={"slot": "2099-01-05 09:00"}),
            session=session,
            user=user,
            calendar=FakeCalendar([_SLOT]),
        )
    )
    assert out["meeting_time"] == "2099-01-05 09:00"
    assert out["meeting_link"].startswith("https://")
    assert out["status"] == "scheduled"


def test_dispatch_create_meeting_rejects_unavailable_slot(session):
    user = _seed_user(session, phone="0823")
    LeadRepository(session).upsert(user.id, project_type="POS")
    out = json.loads(
        dispatch(
            ToolCall(name="create_meeting", args={"slot": "2099-12-31 23:00"}),
            session=session,
            user=user,
            calendar=FakeCalendar([_SLOT]),
        )
    )
    assert "error" in out


def test_dispatch_send_invitation(session):
    user = _seed_user(session, phone="0824", email="b@mail.com")
    lead = LeadRepository(session).upsert(user.id, project_type="POS")
    MeetingRepository(session).create(lead.id, _SLOT, "https://meet.efisien.id/abc")
    mail = FakeEmail()
    out = json.loads(
        dispatch(
            ToolCall(name="send_invitation", args={}),
            session=session,
            user=user,
            email=mail,
        )
    )
    assert mail.sent and mail.sent[0][0] == "b@mail.com"
    assert "terkirim" in out["result"].lower()


from app.repositories.project_repo import ProjectRepository
from app.repositories.ticket_repo import TicketRepository


def test_dispatch_get_project_status_empty(session):
    user = _seed_user(session, phone="0830")
    out = json.loads(
        dispatch(ToolCall(name="get_project_status", args={}), session=session, user=user)
    )
    assert "Belum ada proyek" in out["result"]


def test_dispatch_get_project_status_returns_projects(session):
    user = _seed_user(session, phone="0831")
    ProjectRepository(session).create(
        user.id, name="POS Toko A", type="POS", progress=70,
        status="in_progress", details={"frontend": 80},
    )
    out = json.loads(
        dispatch(ToolCall(name="get_project_status", args={}), session=session, user=user)
    )
    assert out["projects"][0]["name"] == "POS Toko A"
    assert out["projects"][0]["progress"] == 70
    assert out["projects"][0]["details"] == {"frontend": 80}


def test_dispatch_create_ticket_injects_user_and_links_project(session):
    user = _seed_user(session, phone="0832")
    project = ProjectRepository(session).create(user.id, name="Web", type="Website")
    out = json.loads(
        dispatch(
            ToolCall(
                name="create_ticket",
                args={"description": "tidak bisa login", "category": "bug", "priority": "high"},
            ),
            session=session,
            user=user,
        )
    )
    assert out["status"] == "open"
    assert out["category"] == "bug"
    assert out["priority"] == "high"
    assert out["project_id"] == project.id
    ticket = TicketRepository(session).get_latest_for_user(user.id)
    assert ticket.user_id == user.id
    assert ticket.description == "tidak bisa login"


def test_dispatch_create_ticket_invalid_enum_falls_back(session):
    user = _seed_user(session, phone="0833")
    out = json.loads(
        dispatch(
            ToolCall(
                name="create_ticket",
                args={"description": "x", "category": "wut", "priority": "urgent"},
            ),
            session=session,
            user=user,
        )
    )
    assert out["category"] == "question"
    assert out["priority"] == "med"
    assert out["project_id"] is None


def test_dispatch_assign_developer_sets_assigned(session):
    user = _seed_user(session, phone="0834")
    TicketRepository(session).create(
        user.id, description="x", category="bug", priority="med"
    )
    out = json.loads(
        dispatch(ToolCall(name="assign_developer", args={}), session=session, user=user)
    )
    assert out["status"] == "assigned"
    assert out["assigned_developer"] == "Tim Development"


def test_dispatch_assign_developer_no_ticket(session):
    user = _seed_user(session, phone="0835")
    out = json.loads(
        dispatch(ToolCall(name="assign_developer", args={}), session=session, user=user)
    )
    assert "Belum ada tiket" in out["result"]
