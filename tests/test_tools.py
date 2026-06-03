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


def _seed_user(session, phone="0812"):
    user = User(name="Budi", phone=phone)
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
