from app.llm.base import ChatMessage, LLMClient, LLMResponse, ToolSpec


class FakeLLM(LLMClient):
    """Deterministic, scriptable LLM for tests.

    - FakeLLM(reply="...")            -> always returns that text.
    - FakeLLM(responses=[r1, r2, ...]) -> returns each LLMResponse in turn,
      staying on the last one once the script is exhausted.
    """

    def __init__(
        self,
        reply: str | None = None,
        responses: list[LLMResponse] | None = None,
    ) -> None:
        if responses is None:
            text = reply if reply is not None else "Halo! Ada yang bisa saya bantu?"
            responses = [LLMResponse(text=text)]
        self._responses = responses
        self._i = 0
        self.calls: list[tuple[str, list[ChatMessage], list[ToolSpec] | None]] = []

    def generate(self, system, messages, tools=None):
        self.calls.append((system, list(messages), tools))
        resp = self._responses[self._i]
        if self._i < len(self._responses) - 1:
            self._i += 1
        return resp
