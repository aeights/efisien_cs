from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON schema for the tool's arguments


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[ToolCall] | None = None  # assistant turn requesting tools
    tool_name: str | None = None  # tool result turn: which tool produced it


@dataclass
class LLMResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(ABC):
    @abstractmethod
    def generate(
        self,
        system: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse:
        """Return either text or tool-call requests for the given context."""
        ...
