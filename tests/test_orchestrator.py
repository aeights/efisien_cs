from app.agent.orchestrator import handle_chat
from app.llm.fake import FakeLLM
from app.repositories.message_repo import MessageRepository


def test_handle_chat_persists_user_and_assistant_messages(session):
    llm = FakeLLM(reply="Tentu, kami menyediakan banyak layanan.")
    reply, user = handle_chat(
        session, llm, message="Apa saja layanan kalian?", name="Budi", phone="0811"
    )
    assert reply == "Tentu, kami menyediakan banyak layanan."
    stored = MessageRepository(session).recent(user.id, limit=10)
    assert [(m.role, m.content) for m in stored] == [
        ("user", "Apa saja layanan kalian?"),
        ("assistant", "Tentu, kami menyediakan banyak layanan."),
    ]


def test_handle_chat_sends_prior_history_to_llm(session):
    llm = FakeLLM(reply="ok")
    handle_chat(session, llm, message="pesan pertama", phone="0811")
    handle_chat(session, llm, message="pesan kedua", phone="0811")

    _system, sent_messages, _tools = llm.calls[-1]
    assert [m.content for m in sent_messages] == ["pesan pertama", "ok", "pesan kedua"]
