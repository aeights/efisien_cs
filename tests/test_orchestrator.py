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
