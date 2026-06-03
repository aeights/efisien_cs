import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chat import get_llm, get_retriever
from app.db import get_session
from app.llm.base import LLMResponse, ToolCall
from app.llm.fake import FakeLLM
from app.main import app
from app.models.base import Base
from app.models.user import User  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.lead import Lead  # noqa: F401
from app.rag.embeddings import FakeEmbedder
from app.rag.retriever import Retriever
from app.rag.store import ChromaStore


class _EmptyRetriever:
    def search(self, query, k=4):
        return []


@pytest.fixture
def build_client():
    def _build(llm, retriever):
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
        app.dependency_overrides[get_llm] = lambda: llm
        app.dependency_overrides[get_retriever] = lambda: retriever
        return TestClient(app)

    yield _build
    app.dependency_overrides.clear()


def test_chat_endpoint_returns_reply(build_client):
    client = build_client(FakeLLM(reply="Halo dari AI"), _EmptyRetriever())
    resp = client.post("/chat", json={"message": "hai", "phone": "0811"})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "Halo dari AI"


def test_chat_endpoint_requires_identity(build_client):
    client = build_client(FakeLLM(reply="x"), _EmptyRetriever())
    assert client.post("/chat", json={"message": "hai"}).status_code == 422


def test_health_endpoint(build_client):
    client = build_client(FakeLLM(reply="x"), _EmptyRetriever())
    assert client.get("/health").json() == {"status": "ok"}


def test_faq_flow_uses_rag(build_client):
    # Seed an in-memory knowledge base.
    store = ChromaStore.ephemeral()
    emb = FakeEmbedder()
    store.reset()
    docs = ["Layanan kami: ERP, AI, Computer Vision.", "Kontak via WhatsApp."]
    store.add(
        ids=["0", "1"],
        embeddings=emb.embed_documents(docs),
        documents=docs,
        metadatas=[{"source": "profile.txt"}, {"source": "profile.txt"}],
    )
    retriever = Retriever(store, emb)

    # LLM: turn 1 calls the tool, turn 2 answers from the retrieved text.
    scripted = [
        LLMResponse(tool_calls=[ToolCall(name="search_knowledge_base", args={"query": "layanan"})]),
        LLMResponse(text="Layanan kami: ERP, AI, Computer Vision."),
    ]
    client = build_client(FakeLLM(responses=scripted), retriever)

    resp = client.post("/chat", json={"message": "apa saja layanan?", "phone": "0811"})
    assert resp.status_code == 200
    assert "ERP" in resp.json()["reply"]


def test_lead_flow_replies_after_create_lead(build_client):
    scripted = [
        LLMResponse(
            tool_calls=[
                ToolCall(name="create_lead", args={"project_type": "POS", "budget": "20 juta"})
            ]
        ),
        LLMResponse(text="Kebutuhan Anda sudah dicatat, tim kami akan menindaklanjuti."),
    ]
    client = build_client(FakeLLM(responses=scripted), _EmptyRetriever())
    resp = client.post("/chat", json={"message": "mau bikin POS", "phone": "0899"})
    assert resp.status_code == 200
    assert "dicatat" in resp.json()["reply"]
