import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chat import get_llm
from app.db import get_session
from app.llm.fake import FakeLLM
from app.main import app
from app.models.base import Base
from app.models.user import User  # noqa: F401
from app.models.message import Message  # noqa: F401


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with TestSession() as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_llm] = lambda: FakeLLM(reply="Halo dari AI")
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_chat_endpoint_returns_reply(client):
    resp = client.post("/chat", json={"message": "hai", "phone": "0811"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Halo dari AI"
    assert body["user_id"] >= 1


def test_chat_endpoint_requires_identity(client):
    resp = client.post("/chat", json={"message": "hai"})
    assert resp.status_code == 422


def test_health_endpoint(client):
    assert client.get("/health").json() == {"status": "ok"}
