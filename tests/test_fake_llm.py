from app.llm.base import ChatMessage, LLMResponse, ToolCall
from app.llm.fake import FakeLLM


def test_fake_llm_default_text_reply():
    llm = FakeLLM(reply="Halo!")
    resp = llm.generate("SYS", [ChatMessage(role="user", content="hai")])
    assert resp.text == "Halo!"
    assert resp.tool_calls == []
    assert llm.calls[0][0] == "SYS"


def test_fake_llm_scripted_sequence_stays_on_last():
    scripted = [
        LLMResponse(tool_calls=[ToolCall(name="search_knowledge_base", args={"query": "layanan"})]),
        LLMResponse(text="Layanan kami: ERP, AI."),
    ]
    llm = FakeLLM(responses=scripted)
    r1 = llm.generate("SYS", [])
    r2 = llm.generate("SYS", [])
    r3 = llm.generate("SYS", [])
    assert r1.tool_calls[0].name == "search_knowledge_base"
    assert r2.text == "Layanan kami: ERP, AI."
    assert r3.text == "Layanan kami: ERP, AI."
