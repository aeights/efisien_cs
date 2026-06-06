from app.agent.orchestrator import MAX_ITERATIONS, handle_chat
from app.llm.base import LLMResponse, ToolCall
from app.llm.fake import FakeLLM
from app.repositories.message_repo import MessageRepository


class _FakeRetriever:
    def __init__(self, hits=None):
        self._hits = hits if hits is not None else [
            {"text": "Layanan: ERP, AI.", "source": "profile.txt", "score": 0.1}
        ]

    def search(self, query, k=4):
        return self._hits


def test_runs_tool_then_answers_and_persists_only_user_and_final(session):
    scripted = [
        LLMResponse(tool_calls=[ToolCall(name="search_knowledge_base", args={"query": "layanan"})]),
        LLMResponse(text="Layanan kami: ERP, AI."),
    ]
    llm = FakeLLM(responses=scripted)
    reply, user = handle_chat(
        session, llm, _FakeRetriever(), message="apa layanan?", phone="0811"
    )
    assert reply == "Layanan kami: ERP, AI."
    # tools were offered to the LLM
    assert llm.calls[0][2] is not None
    # only the user message and final reply are persisted (tool round-trip is ephemeral)
    stored = MessageRepository(session).recent(user.id, limit=10)
    assert [(m.role, m.content) for m in stored] == [
        ("user", "apa layanan?"),
        ("assistant", "Layanan kami: ERP, AI."),
    ]


def test_direct_answer_without_tool(session):
    llm = FakeLLM(reply="Halo!")
    reply, _user = handle_chat(session, llm, _FakeRetriever(), message="hai", phone="0811")
    assert reply == "Halo!"


def test_max_iterations_guard_when_llm_never_answers(session):
    looping = LLMResponse(tool_calls=[ToolCall(name="search_knowledge_base", args={"query": "x"})])
    llm = FakeLLM(responses=[looping])  # always returns a tool call
    reply, _user = handle_chat(session, llm, _FakeRetriever(), message="loop?", phone="0811")
    assert "maaf" in reply.lower()
    assert len(llm.calls) == MAX_ITERATIONS


def test_create_lead_loop_persists_lead(session):
    scripted = [
        LLMResponse(
            tool_calls=[
                ToolCall(
                    name="create_lead",
                    args={
                        "project_type": "POS",
                        "platform": "Web",
                        "requirements": "3 cabang",
                        "budget": "20 juta",
                    },
                )
            ]
        ),
        LLMResponse(text="Siap, kebutuhan Anda sudah saya catat."),
    ]
    llm = FakeLLM(responses=scripted)
    reply, user = handle_chat(
        session, llm, _FakeRetriever(), message="mau bikin aplikasi POS", phone="0812"
    )
    assert reply == "Siap, kebutuhan Anda sudah saya catat."

    from app.repositories.lead_repo import LeadRepository

    lead = LeadRepository(session).get_latest(user.id)
    assert lead is not None
    assert lead.project_type == "POS"
    assert lead.requirements == {"text": "3 cabang"}
    assert lead.budget == "20 juta"


def test_booking_loop_persists_meeting(session):
    from datetime import datetime

    from app.integrations.calendar import WIB, fmt_slot
    from app.repositories.meeting_repo import MeetingRepository
    from tests.fakes import FakeCalendar, FakeEmail

    slot = datetime(2099, 1, 5, 9, 0, tzinfo=WIB)
    scripted = [
        LLMResponse(tool_calls=[ToolCall(name="create_lead", args={"project_type": "POS"})]),
        LLMResponse(tool_calls=[ToolCall(name="get_available_slots", args={})]),
        LLMResponse(tool_calls=[ToolCall(name="create_meeting", args={"slot": fmt_slot(slot)})]),
        LLMResponse(tool_calls=[ToolCall(name="send_invitation", args={})]),
        LLMResponse(text="Meeting Anda sudah terjadwal."),
    ]
    llm = FakeLLM(responses=scripted)
    mail = FakeEmail()
    reply, user = handle_chat(
        session,
        llm,
        _FakeRetriever(),
        message="mau konsultasi",
        phone="0812",
        calendar=FakeCalendar([slot]),
        mailer=mail,
    )
    assert reply == "Meeting Anda sudah terjadwal."
    meeting = MeetingRepository(session).get_latest_for_user(user.id)
    assert meeting is not None
    assert meeting.meeting_link.startswith("https://")
    assert mail.sent


def test_ticket_loop_creates_and_assigns(session):
    from app.repositories.ticket_repo import TicketRepository

    scripted = [
        LLMResponse(
            tool_calls=[
                ToolCall(
                    name="create_ticket",
                    args={"description": "tidak bisa login", "category": "bug", "priority": "high"},
                )
            ]
        ),
        LLMResponse(tool_calls=[ToolCall(name="assign_developer", args={})]),
        LLMResponse(text="Tiket Anda sudah dibuat dan ditugaskan ke tim kami."),
    ]
    llm = FakeLLM(responses=scripted)
    reply, user = handle_chat(
        session, llm, _FakeRetriever(), message="aplikasi saya error", phone="0860"
    )
    assert "ditugaskan" in reply
    ticket = TicketRepository(session).get_latest_for_user(user.id)
    assert ticket is not None
    assert ticket.status == "assigned"
    assert ticket.category == "bug"
    assert ticket.assigned_developer == "Tim Development"


def test_memory_facts_injected_into_system_prompt(session):
    from app.repositories.client_fact_repo import ClientFactRepository
    from app.repositories.user_repo import UserRepository

    user = UserRepository(session).get_or_create(phone="0873")
    session.flush()
    ClientFactRepository(session).upsert(user.id, "nama", "Budi")
    ClientFactRepository(session).upsert(user.id, "perusahaan", "Toko Maju")

    llm = FakeLLM(reply="Halo Budi!")
    handle_chat(session, llm, _FakeRetriever(), message="hai", phone="0873")

    system_sent = llm.calls[0][0]
    assert "nama: Budi" in system_sent
    assert "perusahaan: Toko Maju" in system_sent


def test_empty_model_reply_uses_fallback(session):
    llm = FakeLLM(responses=[LLMResponse(text="")])
    reply, _user = handle_chat(session, llm, _FakeRetriever(), message="hai", phone="0876")
    assert reply.strip() != ""


def test_remember_fact_loop_persists(session):
    from app.repositories.client_fact_repo import ClientFactRepository

    scripted = [
        LLMResponse(tool_calls=[ToolCall(name="remember_fact", args={"key": "nama", "value": "Budi"})]),
        LLMResponse(text="Senang berkenalan, Budi!"),
    ]
    llm = FakeLLM(responses=scripted)
    reply, user = handle_chat(
        session, llm, _FakeRetriever(), message="nama saya Budi", phone="0874"
    )
    facts = ClientFactRepository(session).list_for_user(user.id)
    assert any(f.key == "nama" and f.value == "Budi" for f in facts)


def test_handoff_loop_persists_notification(session):
    from sqlalchemy import select

    from app.models.notification import Notification

    scripted = [
        LLMResponse(tool_calls=[ToolCall(name="notify_manager", args={"reason": "komplain pembayaran"})]),
        LLMResponse(text="Saya teruskan ke tim kami."),
    ]
    llm = FakeLLM(responses=scripted)
    reply, user = handle_chat(
        session, llm, _FakeRetriever(), message="saya mau komplain", phone="0875"
    )
    notifs = session.scalars(select(Notification)).all()
    assert len(notifs) == 1
    assert notifs[0].target_role == "manager"
    assert notifs[0].payload["phone"] == "0875"
