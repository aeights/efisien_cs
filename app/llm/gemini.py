from google import genai
from google.genai import types

from app.config import settings
from app.llm.base import ChatMessage, LLMClient, LLMResponse, ToolCall, ToolSpec


class GeminiLLM(LLMClient):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.client = genai.Client(api_key=api_key or settings.gemini_api_key)
        self.model = model or settings.gemini_model

    def _to_contents(self, messages: list[ChatMessage]) -> list[types.Content]:
        contents: list[types.Content] = []
        for m in messages:
            if m.role == "tool":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=m.tool_name, response={"output": m.content}
                            )
                        ],
                    )
                )
            elif m.role == "assistant" and m.tool_calls:
                contents.append(
                    types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(name=tc.name, args=tc.args)
                            for tc in m.tool_calls
                        ],
                    )
                )
            else:
                role = "model" if m.role == "assistant" else "user"
                contents.append(
                    types.Content(role=role, parts=[types.Part.from_text(text=m.content)])
                )
        return contents

    def _to_tools(self, tools: list[ToolSpec] | None):
        if not tools:
            return None
        declarations = [
            types.FunctionDeclaration(
                name=t.name, description=t.description, parameters_json_schema=t.parameters
            )
            for t in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    def generate(self, system, messages, tools=None):
        response = self.client.models.generate_content(
            model=self.model,
            contents=self._to_contents(messages),
            config=types.GenerateContentConfig(
                system_instruction=system, tools=self._to_tools(tools)
            ),
        )
        calls = response.function_calls or []
        if calls:
            return LLMResponse(
                tool_calls=[ToolCall(name=c.name, args=dict(c.args or {})) for c in calls]
            )
        return LLMResponse(text=response.text or "")
