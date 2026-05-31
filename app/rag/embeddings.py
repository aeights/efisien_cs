from abc import ABC, abstractmethod

from google import genai
from google.genai import types

from app.config import settings


class Embedder(ABC):
    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        ...


class GeminiEmbedder(Embedder):
    def __init__(self, api_key: str | None = None, model: str = "text-embedding-004") -> None:
        self.client = genai.Client(api_key=api_key or settings.gemini_api_key)
        self.model = model

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        resp = self.client.models.embed_content(
            model=self.model,
            contents=texts,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        return [e.values for e in resp.embeddings]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


class FakeEmbedder(Embedder):
    """Deterministic keyword-count embedder for tests (no network)."""

    VOCAB = [
        "layanan", "harga", "erp", "ai", "kontak",
        "website", "mobile", "portofolio", "visi", "misi",
    ]

    def _vec(self, text: str) -> list[float]:
        t = text.lower()
        # +1.0 bias dim so vectors are never all-zero (cosine stays defined)
        return [float(t.count(w)) for w in self.VOCAB] + [1.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)
