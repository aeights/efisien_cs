from app.integrations.whatsapp import WahaClient


class _FakeResp:
    def raise_for_status(self):
        return None


class _FakeHttpx:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResp()


def test_waha_send_text():
    fake = _FakeHttpx()
    waha = WahaClient(base_url="http://waha:3000", session="default", api_key="secret", client=fake)
    waha.send_text("628111@c.us", "halo")
    call = fake.calls[-1]
    assert call["url"] == "http://waha:3000/api/sendText"
    assert call["json"] == {"session": "default", "chatId": "628111@c.us", "text": "halo"}
    assert call["headers"]["X-Api-Key"] == "secret"


from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chat import get_calendar, get_email, get_llm, get_retriever, get_waha_client
from app.db import get_session
from app.llm.fake import FakeLLM
from app.main import app
from app.models.base import Base
from app.models.user import User  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.lead import Lead  # noqa: F401
from app.models.meeting import Meeting  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.ticket import Ticket  # noqa: F401
from app.models.client_fact import ClientFact  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from tests.fakes import FakeCalendar, FakeEmail


class _EmptyRetriever:
    def search(self, query, k=4):
        return []


class _CapturingWaha:
    def __init__(self):
        self.sent = []

    def send_text(self, chat_id, text):
        self.sent.append((chat_id, text))


def _webhook_client(llm, waha):
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with TestSession() as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_retriever] = lambda: _EmptyRetriever()
    app.dependency_overrides[get_calendar] = lambda: FakeCalendar([])
    app.dependency_overrides[get_email] = lambda: FakeEmail()
    app.dependency_overrides[get_waha_client] = lambda: waha
    return TestClient(app)


def test_webhook_processes_message_and_replies():
    waha = _CapturingWaha()
    client = _webhook_client(FakeLLM(reply="Halo!"), waha)
    payload = {"event": "message", "payload": {"from": "628111@c.us", "body": "halo", "fromMe": False}}
    r = client.post("/webhook/whatsapp", json=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert waha.sent == [("628111@c.us", "Halo!")]
    app.dependency_overrides.clear()


def test_webhook_ignores_fromme_and_groups():
    waha = _CapturingWaha()
    client = _webhook_client(FakeLLM(reply="x"), waha)
    fromme = {"event": "message", "payload": {"from": "628@c.us", "body": "hi", "fromMe": True}}
    group = {"event": "message", "payload": {"from": "123@g.us", "body": "hi", "fromMe": False}}
    assert client.post("/webhook/whatsapp", json=fromme).json()["status"] == "ignored"
    assert client.post("/webhook/whatsapp", json=group).json()["status"] == "ignored"
    assert waha.sent == []
    app.dependency_overrides.clear()


class _FailingWaha:
    def send_text(self, chat_id, text):
        raise RuntimeError("waha down")


def test_webhook_returns_ok_even_if_send_fails():
    client = _webhook_client(FakeLLM(reply="Halo!"), _FailingWaha())
    payload = {"event": "message", "payload": {"from": "628111@c.us", "body": "halo", "fromMe": False}}
    r = client.post("/webhook/whatsapp", json=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    app.dependency_overrides.clear()
