from app.llm.base import ChatMessage, LLMClient


class FakeLLM(LLMClient):
    """Deterministic LLM for tests — no network calls."""

    def __init__(self, reply: str = "Halo! Ada yang bisa saya bantu?") -> None:
        self.reply = reply
        self.last_system: str | None = None
        self.last_messages: list[ChatMessage] | None = None

    def generate(self, system: str, messages: list[ChatMessage]) -> str:
        self.last_system = system
        self.last_messages = messages
        return self.reply
