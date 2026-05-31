from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


class LLMClient(ABC):
    @abstractmethod
    def generate(self, system: str, messages: list[ChatMessage]) -> str:
        """Return the assistant's text reply given a system prompt and history."""
        ...
