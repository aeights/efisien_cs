import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chat import get_calendar, get_email, get_llm, get_retriever
from app.db import get_session
from app.llm.base import LLMResponse, ToolCall
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
from app.rag.embeddings import FakeEmbedder
from app.rag.retriever import Retriever
from app.rag.store import ChromaStore
from tests.fakes import FakeCalendar, FakeEmail


class _EmptyRetriever:
    def search(self, query, k=4):
        return []


@pytest.fixture
def build_client():
    def _build(llm, retriever, calendar=None, email=None):
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
        app.dependency_overrides[get_calendar] = lambda: calendar or FakeCalendar([])
        app.dependency_overrides[get_email] = lambda: email or FakeEmail()
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


def test_booking_flow_replies_after_create_meeting(build_client):
    from datetime import datetime

    from app.integrations.calendar import WIB, fmt_slot

    slot = datetime(2099, 1, 5, 9, 0, tzinfo=WIB)
    scripted = [
        LLMResponse(tool_calls=[ToolCall(name="create_lead", args={"project_type": "POS"})]),
        LLMResponse(tool_calls=[ToolCall(name="get_available_slots", args={})]),
        LLMResponse(tool_calls=[ToolCall(name="create_meeting", args={"slot": fmt_slot(slot)})]),
        LLMResponse(text="Meeting Anda terjadwal pada 2099-01-05 09:00 WIB."),
    ]
    client = build_client(
        FakeLLM(responses=scripted), _EmptyRetriever(), calendar=FakeCalendar([slot])
    )
    resp = client.post("/chat", json={"message": "mau konsultasi", "phone": "0899"})
    assert resp.status_code == 200
    assert "terjadwal" in resp.json()["reply"]


def test_ticket_flow_via_chat(build_client):
    scripted = [
        LLMResponse(
            tool_calls=[
                ToolCall(
                    name="create_ticket",
                    args={"description": "error login", "category": "bug", "priority": "high"},
                )
            ]
        ),
        LLMResponse(tool_calls=[ToolCall(name="assign_developer", args={})]),
        LLMResponse(text="Tiket Anda sudah dibuat dan ditugaskan."),
    ]
    client = build_client(FakeLLM(responses=scripted), _EmptyRetriever())
    resp = client.post("/chat", json={"message": "aplikasi error", "phone": "0861"})
    assert resp.status_code == 200
    assert "ditugaskan" in resp.json()["reply"]


def test_project_status_flow_via_chat(build_client):
    scripted = [
        LLMResponse(tool_calls=[ToolCall(name="get_project_status", args={})]),
        LLMResponse(text="Status proyek Anda sudah saya cek."),
    ]
    client = build_client(FakeLLM(responses=scripted), _EmptyRetriever())
    resp = client.post("/chat", json={"message": "gimana proyek saya?", "phone": "0862"})
    assert resp.status_code == 200
    assert "proyek" in resp.json()["reply"].lower()


def test_handoff_flow_via_chat(build_client):
    scripted = [
        LLMResponse(
            tool_calls=[
                ToolCall(name="notify_manager", args={"reason": "klien minta bicara dengan manusia"})
            ]
        ),
        LLMResponse(text="Baik, saya teruskan ke tim kami. Mohon ditunggu."),
    ]
    client = build_client(FakeLLM(responses=scripted), _EmptyRetriever())
    resp = client.post("/chat", json={"message": "saya mau bicara dengan orang", "phone": "0864"})
    assert resp.status_code == 200
    assert "tim" in resp.json()["reply"].lower()


def test_full_workflow_faq_lead_proposal_booking(build_client):
    from datetime import datetime

    from app.integrations.calendar import WIB, fmt_slot

    slot = datetime(2099, 1, 5, 9, 0, tzinfo=WIB)
    # One scripted FakeLLM drives the whole journey; it advances across POSTs.
    scripted = [
        # 1) FAQ
        LLMResponse(tool_calls=[ToolCall(name="search_knowledge_base", args={"query": "layanan"})]),
        LLMResponse(text="Layanan kami: ERP, AI, dan pengembangan aplikasi."),
        # 2) Lead
        LLMResponse(
            tool_calls=[
                ToolCall(name="create_lead", args={"project_type": "POS", "requirements": "3 cabang", "budget": "25 juta"})
            ]
        ),
        LLMResponse(text="Kebutuhan Anda sudah dicatat."),
        # 3) Proposal
        LLMResponse(
            tool_calls=[
                ToolCall(
                    name="generate_proposal",
                    args={"scope": "POS 3 cabang", "timeline": "6-8 minggu", "cost": "Rp 25 juta", "deliverables": ["Aplikasi POS"]},
                )
            ]
        ),
        LLMResponse(text="Berikut proposal Anda: scope POS 3 cabang, estimasi Rp 25 juta."),
        # 4) Booking
        LLMResponse(tool_calls=[ToolCall(name="get_available_slots", args={})]),
        LLMResponse(tool_calls=[ToolCall(name="create_meeting", args={"slot": fmt_slot(slot)})]),
        LLMResponse(text="Konsultasi Anda terjadwal."),
    ]
    client = build_client(
        FakeLLM(responses=scripted), _EmptyRetriever(), calendar=FakeCalendar([slot])
    )

    r1 = client.post("/chat", json={"message": "Apa layanan kalian?", "phone": "0890"})
    assert r1.status_code == 200
    assert "Layanan" in r1.json()["reply"]

    r2 = client.post("/chat", json={"message": "Mau bikin POS 3 cabang, budget 25 juta", "phone": "0890"})
    assert r2.status_code == 200
    assert "dicatat" in r2.json()["reply"]

    r3 = client.post("/chat", json={"message": "Tolong buatkan proposal", "phone": "0890"})
    assert r3.status_code == 200
    assert "proposal" in r3.json()["reply"].lower()

    r4 = client.post("/chat", json={"message": "Sekalian jadwalkan konsultasi", "phone": "0890"})
    assert r4.status_code == 200
    assert "terjadwal" in r4.json()["reply"]
