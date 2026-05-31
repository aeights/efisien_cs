from app.llm.base import ChatMessage
from app.llm.fake import FakeLLM


def test_fake_llm_returns_canned_reply_and_records_input():
    llm = FakeLLM(reply="Halo! Ada yang bisa dibantu?")
    messages = [ChatMessage(role="user", content="hai")]
    out = llm.generate("SYSTEM", messages)
    assert out == "Halo! Ada yang bisa dibantu?"
    assert llm.last_system == "SYSTEM"
    assert llm.last_messages == messages
