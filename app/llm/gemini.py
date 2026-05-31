from google import genai
from google.genai import types

from app.config import settings
from app.llm.base import ChatMessage, LLMClient


class GeminiLLM(LLMClient):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.client = genai.Client(api_key=api_key or settings.gemini_api_key)
        self.model = model or settings.gemini_model

    def generate(self, system: str, messages: list[ChatMessage]) -> str:
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part.from_text(text=m.content)],
            )
            for m in messages
        ]
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        return response.text or ""
