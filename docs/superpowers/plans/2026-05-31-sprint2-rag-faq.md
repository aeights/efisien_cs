# Sprint 2 — RAG FAQ + Tool-Calling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Learning note:** Explain each task in **Bahasa Indonesia** during execution (memory `explain-implementation-in-bahasa`). Code/comments in English; teaching in Bahasa.

**Goal:** Add the FAQ Assistant via RAG (txt → Chroma → grounded answers) and introduce the tool-calling loop into the orchestrator — the foundation for Sprints 3–7.

**Architecture:** A new `rag/` package (embedder, Chroma store, chunking, ingest, retriever). The `LLMClient` interface is upgraded to be tool-aware (`generate(system, messages, tools) -> LLMResponse`). The orchestrator gains a bounded tool-calling loop. `search_knowledge_base` is the first registered tool. Company identity is corrected to **PT Efisien Integrasi Indonesia**.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, Gemini (`google-genai` 2.7.0), `text-embedding-004`, **chromadb 1.5.9** (verified working on 3.14 with explicit embeddings), pytest. Tests use a `FakeEmbedder` + in-memory Chroma + scriptable `FakeLLM` — no real API calls.

**Verified API facts (used below):**
- `client.models.embed_content(model=..., contents=[...], config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"|"RETRIEVAL_QUERY"))` → `resp.embeddings[i].values`.
- `client.models.generate_content(..., config=types.GenerateContentConfig(system_instruction=..., tools=[types.Tool(function_declarations=[...])]))`; parse `resp.function_calls` (list of `FunctionCall` with `.name`, `.args`) and `resp.text`.
- `types.FunctionDeclaration(name=, description=, parameters_json_schema=<dict>)`.
- `types.Part.from_function_call(name=, args=)`, `types.Part.from_function_response(name=, response=<dict>)`.
- chromadb: `PersistentClient(path=)` / `EphemeralClient()`; `get_or_create_collection(name, metadata={"hnsw:space":"cosine"})`; `.add(ids=, embeddings=, documents=, metadatas=)`; `.query(query_embeddings=[v], n_results=k)` → `{documents, metadatas, distances}` (list-of-lists); `client.delete_collection(name)`. Collection name 3–512 chars.

---

### Task 1: Add chromadb dependency

**Files:**
- Modify: `pyproject.toml` (via `uv add`)

- [ ] **Step 1: Add chromadb**

Run: `uv add chromadb`
Expected: `pyproject.toml` gains `chromadb>=1.5` under dependencies; `uv.lock` updated.

- [ ] **Step 2: Verify import**

Run: `uv run python -c "import chromadb; print(chromadb.__version__)"`
Expected: prints `1.5.9` (or newer).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add chromadb dependency"
```

---

### Task 2: Embedder interface + FakeEmbedder + GeminiEmbedder

**Files:**
- Create: `app/rag/__init__.py` (empty)
- Create: `app/rag/embeddings.py`
- Test: `tests/test_embeddings.py`

- [ ] **Step 1: Create `app/rag/__init__.py`** (empty file)

- [ ] **Step 2: Write the failing test — `tests/test_embeddings.py`**

```python
from app.rag.embeddings import FakeEmbedder


def test_fake_embedder_is_deterministic_and_same_dim():
    emb = FakeEmbedder()
    a = emb.embed_query("apa saja layanan kami")
    b = emb.embed_query("apa saja layanan kami")
    assert a == b
    docs = emb.embed_documents(["layanan erp", "kontak website"])
    assert len(docs) == 2
    assert len(docs[0]) == len(a)  # query and document vectors share dimension


def test_fake_embedder_reflects_shared_keywords():
    emb = FakeEmbedder()
    q = emb.embed_query("layanan")
    doc_match = emb.embed_documents(["layanan kami banyak"])[0]
    doc_other = emb.embed_documents(["kontak whatsapp"])[0]
    # the "layanan" dimension is non-zero for the matching doc, zero for the other
    idx = FakeEmbedder.VOCAB.index("layanan")
    assert q[idx] > 0 and doc_match[idx] > 0
    assert doc_other[idx] == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_embeddings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.rag.embeddings'`

- [ ] **Step 4: Implement `app/rag/embeddings.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_embeddings.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add app/rag/__init__.py app/rag/embeddings.py tests/test_embeddings.py
git commit -m "feat: Embedder interface, GeminiEmbedder, and FakeEmbedder"
```

---

### Task 3: Chroma store wrapper

**Files:**
- Create: `app/rag/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write the failing test — `tests/test_store.py`**

```python
from app.rag.store import ChromaStore


def test_add_and_query_returns_documents_and_sources():
    store = ChromaStore.ephemeral()
    store.reset()
    store.add(
        ids=["0", "1"],
        embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        documents=["layanan kami banyak", "kontak whatsapp"],
        metadatas=[{"source": "services.txt"}, {"source": "contact.txt"}],
    )
    assert store.count() == 2
    hits = store.query([0.9, 0.1, 0.0], k=2)
    assert hits[0]["text"] == "layanan kami banyak"
    assert hits[0]["source"] == "services.txt"
    assert "score" in hits[0]


def test_reset_clears_collection():
    store = ChromaStore.ephemeral()
    store.reset()
    store.add(ids=["0"], embeddings=[[1.0, 0.0]], documents=["x"], metadatas=[{"source": "a"}])
    store.reset()
    assert store.count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.rag.store'`

- [ ] **Step 3: Implement `app/rag/store.py`**

```python
import chromadb


class ChromaStore:
    """Thin wrapper over a Chroma collection using explicit (precomputed) embeddings."""

    def __init__(self, client, collection_name: str = "company_docs") -> None:
        self.client = client
        self.collection_name = collection_name

    @classmethod
    def persistent(cls, path: str = "data/chroma", collection_name: str = "company_docs") -> "ChromaStore":
        return cls(chromadb.PersistentClient(path=path), collection_name)

    @classmethod
    def ephemeral(cls, collection_name: str = "company_docs") -> "ChromaStore":
        return cls(chromadb.EphemeralClient(), collection_name)

    def _collection(self):
        return self.client.get_or_create_collection(
            self.collection_name, metadata={"hnsw:space": "cosine"}
        )

    def reset(self):
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        return self._collection()

    def add(self, ids, embeddings, documents, metadatas) -> None:
        self._collection().add(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )

    def count(self) -> int:
        return self._collection().count()

    def query(self, embedding: list[float], k: int = 4) -> list[dict]:
        res = self._collection().query(query_embeddings=[embedding], n_results=k)
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res["distances"][0]
        return [
            {"text": doc, "source": (meta or {}).get("source"), "score": dist}
            for doc, meta, dist in zip(docs, metas, dists)
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_store.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/rag/store.py tests/test_store.py
git commit -m "feat: ChromaStore wrapper with explicit embeddings"
```

---

### Task 4: Chunking

**Files:**
- Create: `app/rag/chunking.py`
- Test: `tests/test_chunking.py`

- [ ] **Step 1: Write the failing test — `tests/test_chunking.py`**

```python
from app.rag.chunking import chunk_text


def test_short_text_is_single_chunk():
    chunks = chunk_text("Halo dunia.\n\nIni singkat.", max_chars=600)
    assert len(chunks) == 1
    assert "Halo dunia." in chunks[0]


def test_groups_paragraphs_with_overlap():
    text = "\n\n".join(["a" * 100, "b" * 100, "c" * 100, "d" * 100])
    chunks = chunk_text(text, max_chars=250)
    assert len(chunks) == 3
    assert chunks[0].startswith("a" * 100)
    # overlap: last paragraph of a chunk reappears at the start of the next
    assert "b" * 100 in chunks[0] and "b" * 100 in chunks[1]
    assert "c" * 100 in chunks[1] and "c" * 100 in chunks[2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chunking.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.rag.chunking'`

- [ ] **Step 3: Implement `app/rag/chunking.py`**

```python
import re


def chunk_text(text: str, max_chars: int = 600) -> list[str]:
    """Split text into chunks by grouping blank-line paragraphs up to max_chars,
    keeping a one-paragraph overlap between consecutive chunks."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current and current_len + len(para) > max_chars:
            chunks.append("\n\n".join(current))
            current = [current[-1]]  # overlap: keep last paragraph
            current_len = len(current[-1])
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))
    return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_chunking.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/rag/chunking.py tests/test_chunking.py
git commit -m "feat: paragraph-based text chunking with overlap"
```

---

### Task 5: Ingest pipeline + CLI script

**Files:**
- Create: `app/rag/ingest.py`
- Create: `scripts/ingest_docs.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing test — `tests/test_ingest.py`**

```python
from app.rag.embeddings import FakeEmbedder
from app.rag.ingest import build_chunks, ingest, load_documents
from app.rag.store import ChromaStore


def test_load_and_chunk_documents(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "services.txt").write_text(
        "Layanan kami ERP dan AI.\n\nKami juga buat website.", encoding="utf-8"
    )
    documents = load_documents(str(docs_dir))
    assert documents[0][0] == "services.txt"

    chunks = build_chunks(documents)
    assert chunks[0]["source"] == "services.txt"
    assert chunks[0]["chunk_index"] == 0
    assert "id" in chunks[0] and "text" in chunks[0]


def test_ingest_builds_index(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "services.txt").write_text("Layanan kami ERP.", encoding="utf-8")
    (docs_dir / "contact.txt").write_text("Kontak via website.", encoding="utf-8")

    store = ChromaStore.ephemeral()
    stats = ingest(store, FakeEmbedder(), docs_dir=str(docs_dir))

    assert stats["files"] == 2
    assert stats["chunks"] >= 2
    assert store.count() == stats["chunks"]


def test_ingest_is_idempotent(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.txt").write_text("Layanan ERP.", encoding="utf-8")
    store = ChromaStore.ephemeral()
    ingest(store, FakeEmbedder(), docs_dir=str(docs_dir))
    count_after_first = store.count()
    ingest(store, FakeEmbedder(), docs_dir=str(docs_dir))
    assert store.count() == count_after_first  # rebuild, not duplicate
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.rag.ingest'`

- [ ] **Step 3: Implement `app/rag/ingest.py`**

```python
import pathlib

from app.rag.chunking import chunk_text
from app.rag.embeddings import Embedder
from app.rag.store import ChromaStore


def load_documents(docs_dir: str = "data/docs") -> list[tuple[str, str]]:
    """Return [(source_filename, text), ...] for every *.txt in docs_dir."""
    out: list[tuple[str, str]] = []
    for path in sorted(pathlib.Path(docs_dir).glob("*.txt")):
        out.append((path.name, path.read_text(encoding="utf-8")))
    return out


def build_chunks(documents: list[tuple[str, str]]) -> list[dict]:
    chunks: list[dict] = []
    for source, text in documents:
        for i, piece in enumerate(chunk_text(text)):
            chunks.append(
                {"id": f"{source}::{i}", "text": piece, "source": source, "chunk_index": i}
            )
    return chunks


def ingest(store: ChromaStore, embedder: Embedder, docs_dir: str = "data/docs") -> dict:
    documents = load_documents(docs_dir)
    chunks = build_chunks(documents)
    store.reset()
    if chunks:
        embeddings = embedder.embed_documents([c["text"] for c in chunks])
        store.add(
            ids=[c["id"] for c in chunks],
            embeddings=embeddings,
            documents=[c["text"] for c in chunks],
            metadatas=[
                {"source": c["source"], "chunk_index": c["chunk_index"]} for c in chunks
            ],
        )
    return {"files": len(documents), "chunks": len(chunks)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: 3 passed

- [ ] **Step 5: Create `scripts/ingest_docs.py`**

```python
import pathlib
import sys

# Allow running as `python scripts/ingest_docs.py` from the project root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.rag.embeddings import GeminiEmbedder  # noqa: E402
from app.rag.ingest import ingest  # noqa: E402
from app.rag.store import ChromaStore  # noqa: E402


def main() -> None:
    store = ChromaStore.persistent()
    stats = ingest(store, GeminiEmbedder())
    print(f"{stats['files']} file, {stats['chunks']} chunk, tersimpan ke data/chroma/")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```bash
git add app/rag/ingest.py scripts/ingest_docs.py tests/test_ingest.py
git commit -m "feat: RAG ingestion pipeline and ingest_docs CLI"
```

---

### Task 6: Retriever

**Files:**
- Create: `app/rag/retriever.py`
- Test: `tests/test_retriever.py`

- [ ] **Step 1: Write the failing test — `tests/test_retriever.py`**

```python
from app.rag.embeddings import FakeEmbedder
from app.rag.retriever import Retriever
from app.rag.store import ChromaStore


def _seeded_retriever():
    store = ChromaStore.ephemeral()
    emb = FakeEmbedder()
    store.reset()
    docs = ["Layanan kami meliputi ERP dan AI.", "Kontak kami via website."]
    store.add(
        ids=["0", "1"],
        embeddings=emb.embed_documents(docs),
        documents=docs,
        metadatas=[{"source": "services.txt"}, {"source": "contact.txt"}],
    )
    return Retriever(store, emb)


def test_search_returns_most_relevant_chunk_first():
    retriever = _seeded_retriever()
    hits = retriever.search("apa saja layanan", k=1)
    assert hits[0]["source"] == "services.txt"


def test_search_on_empty_index_returns_empty():
    store = ChromaStore.ephemeral()
    store.reset()
    retriever = Retriever(store, FakeEmbedder())
    assert retriever.search("layanan") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_retriever.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.rag.retriever'`

- [ ] **Step 3: Implement `app/rag/retriever.py`**

```python
from app.rag.embeddings import Embedder
from app.rag.store import ChromaStore


class Retriever:
    def __init__(self, store: ChromaStore, embedder: Embedder) -> None:
        self.store = store
        self.embedder = embedder

    def search(self, query: str, k: int = 4) -> list[dict]:
        if self.store.count() == 0:
            return []
        vector = self.embedder.embed_query(query)
        return self.store.query(vector, k=k)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_retriever.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/rag/retriever.py tests/test_retriever.py
git commit -m "feat: RAG retriever (embed query + similarity search)"
```

---

### Task 7: Upgrade LLM interface to tool-aware types (refactor, behavior unchanged)

This changes `generate` to return `LLMResponse` and accept `tools`. It updates `base.py`, `fake.py`, `gemini.py`, `orchestrator.py`, and their Sprint 1 tests together so the full suite stays green. No tool-calling loop yet.

**Files:**
- Modify: `app/llm/base.py`
- Modify: `app/llm/fake.py`
- Modify: `app/llm/gemini.py`
- Modify: `app/agent/orchestrator.py`
- Modify: `tests/test_fake_llm.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: Replace `app/llm/base.py`**

```python
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
```

- [ ] **Step 2: Replace `app/llm/fake.py`**

```python
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
```

- [ ] **Step 3: Replace `tests/test_fake_llm.py`**

```python
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
```

- [ ] **Step 4: Replace `app/llm/gemini.py`**

```python
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
```

- [ ] **Step 5: Update `app/agent/orchestrator.py` to use `LLMResponse` (still no loop)**

Replace the body so the LLM call uses the new return type. Full file:

```python
from sqlalchemy.orm import Session

from app.agent.prompts import SYSTEM_PROMPT
from app.llm.base import ChatMessage, LLMClient
from app.models.user import User
from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository

HISTORY_LIMIT = 15


def handle_chat(
    session: Session,
    llm: LLMClient,
    *,
    message: str,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> tuple[str, User]:
    users = UserRepository(session)
    messages = MessageRepository(session)

    user = users.get_or_create(name=name, phone=phone, email=email)

    history = messages.recent(user.id, limit=HISTORY_LIMIT)
    llm_messages = [ChatMessage(role=m.role, content=m.content) for m in history]
    llm_messages.append(ChatMessage(role="user", content=message))

    response = llm.generate(SYSTEM_PROMPT, llm_messages)
    reply = response.text or ""

    messages.add(user.id, "user", message)
    messages.add(user.id, "assistant", reply)
    session.commit()

    return reply, user
```

- [ ] **Step 6: Update `tests/test_orchestrator.py` for the new FakeLLM**

```python
from app.agent.orchestrator import handle_chat
from app.llm.fake import FakeLLM
from app.repositories.message_repo import MessageRepository


def test_handle_chat_persists_user_and_assistant_messages(session):
    llm = FakeLLM(reply="Tentu, kami menyediakan banyak layanan.")
    reply, user = handle_chat(
        session, llm, message="Apa saja layanan kalian?", name="Budi", phone="0811"
    )
    assert reply == "Tentu, kami menyediakan banyak layanan."
    stored = MessageRepository(session).recent(user.id, limit=10)
    assert [(m.role, m.content) for m in stored] == [
        ("user", "Apa saja layanan kalian?"),
        ("assistant", "Tentu, kami menyediakan banyak layanan."),
    ]


def test_handle_chat_sends_prior_history_to_llm(session):
    llm = FakeLLM(reply="ok")
    handle_chat(session, llm, message="pesan pertama", phone="0811")
    handle_chat(session, llm, message="pesan kedua", phone="0811")

    _system, sent_messages, _tools = llm.calls[-1]
    assert [m.content for m in sent_messages] == ["pesan pertama", "ok", "pesan kedua"]
```

- [ ] **Step 7: Run the full suite — everything stays green**

Run: `uv run pytest -q`
Expected: all tests pass (Sprint 1 tests now on the new types + Sprint 2 Tasks 2–6 tests).

- [ ] **Step 8: Commit**

```bash
git add app/llm/base.py app/llm/fake.py app/llm/gemini.py app/agent/orchestrator.py tests/test_fake_llm.py tests/test_orchestrator.py
git commit -m "refactor: tool-aware LLMClient interface (LLMResponse + tools), behavior unchanged"
```

---

### Task 8: Tools registry + dispatcher

**Files:**
- Create: `app/agent/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing test — `tests/test_tools.py`**

```python
import json

from app.agent.tools import TOOL_SPECS, dispatch
from app.llm.base import ToolCall


class _FakeRetriever:
    def __init__(self, hits):
        self._hits = hits

    def search(self, query, k=4):
        return self._hits


def test_tool_specs_include_search():
    assert any(t.name == "search_knowledge_base" for t in TOOL_SPECS)


def test_dispatch_search_returns_results():
    retriever = _FakeRetriever([{"text": "Layanan ERP", "source": "profile.txt", "score": 0.1}])
    out = json.loads(
        dispatch(ToolCall(name="search_knowledge_base", args={"query": "layanan"}), retriever=retriever)
    )
    assert out["results"][0]["source"] == "profile.txt"
    assert out["results"][0]["text"] == "Layanan ERP"


def test_dispatch_empty_hits_reports_no_info():
    out = json.loads(
        dispatch(ToolCall(name="search_knowledge_base", args={"query": "x"}), retriever=_FakeRetriever([]))
    )
    assert "result" in out and "Tidak ada" in out["result"]


def test_dispatch_unknown_tool():
    out = json.loads(dispatch(ToolCall(name="nope", args={}), retriever=_FakeRetriever([])))
    assert "error" in out


def test_dispatch_handles_tool_exception():
    class Boom:
        def search(self, query, k=4):
            raise RuntimeError("boom")

    out = json.loads(
        dispatch(ToolCall(name="search_knowledge_base", args={"query": "x"}), retriever=Boom())
    )
    assert out["error"] == "boom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.tools'`

- [ ] **Step 3: Implement `app/agent/tools.py`**

```python
import json

from app.llm.base import ToolCall, ToolSpec

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="search_knowledge_base",
        description=(
            "Cari informasi resmi perusahaan (layanan, harga, profil, portofolio, FAQ) "
            "dari knowledge base. Gunakan untuk pertanyaan tentang perusahaan."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Pertanyaan atau kata kunci pencarian",
                }
            },
            "required": ["query"],
        },
    )
]


def dispatch(tool_call: ToolCall, *, retriever) -> str:
    """Execute a tool call and return a JSON string result to feed back to the LLM."""
    try:
        if tool_call.name == "search_knowledge_base":
            query = tool_call.args.get("query", "")
            hits = retriever.search(query, k=4)
            if not hits:
                return json.dumps(
                    {"result": "Tidak ada informasi relevan di knowledge base."},
                    ensure_ascii=False,
                )
            return json.dumps(
                {"results": [{"text": h["text"], "source": h["source"]} for h in hits]},
                ensure_ascii=False,
            )
        return json.dumps(
            {"error": f"Tool tidak dikenal: {tool_call.name}"}, ensure_ascii=False
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tools.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/agent/tools.py tests/test_tools.py
git commit -m "feat: tools registry and dispatcher with search_knowledge_base"
```

---

### Task 9: Orchestrator tool-calling loop

**Files:**
- Modify: `app/agent/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests — replace `tests/test_orchestrator.py`**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: FAIL — `ImportError: cannot import name 'MAX_ITERATIONS'` (and signature mismatch).

- [ ] **Step 3: Replace `app/agent/orchestrator.py` with the tool-calling loop**

```python
from sqlalchemy.orm import Session

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOL_SPECS, dispatch
from app.llm.base import ChatMessage, LLMClient
from app.models.user import User
from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository

HISTORY_LIMIT = 15
MAX_ITERATIONS = 6
FALLBACK_REPLY = (
    "Mohon maaf, saya sedang mengalami kendala memproses permintaan Anda. "
    "Boleh saya hubungkan dengan tim kami?"
)


def handle_chat(
    session: Session,
    llm: LLMClient,
    retriever,
    *,
    message: str,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> tuple[str, User]:
    users = UserRepository(session)
    messages = MessageRepository(session)

    user = users.get_or_create(name=name, phone=phone, email=email)

    history = messages.recent(user.id, limit=HISTORY_LIMIT)
    convo = [ChatMessage(role=m.role, content=m.content) for m in history]
    convo.append(ChatMessage(role="user", content=message))

    reply = FALLBACK_REPLY
    for _ in range(MAX_ITERATIONS):
        response = llm.generate(SYSTEM_PROMPT, convo, tools=TOOL_SPECS)
        if response.tool_calls:
            convo.append(ChatMessage(role="assistant", tool_calls=response.tool_calls))
            for tool_call in response.tool_calls:
                result = dispatch(tool_call, retriever=retriever)
                convo.append(
                    ChatMessage(role="tool", tool_name=tool_call.name, content=result)
                )
            continue
        reply = response.text or ""
        break

    messages.add(user.id, "user", message)
    messages.add(user.id, "assistant", reply)
    session.commit()

    return reply, user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/agent/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: bounded tool-calling loop in the orchestrator"
```

---

### Task 10: System prompt (Efisien) + /chat wiring + end-to-end RAG test

**Files:**
- Modify: `app/agent/prompts.py`
- Modify: `app/api/chat.py`
- Modify: `tests/test_chat_api.py`

- [ ] **Step 1: Replace `app/agent/prompts.py` with the Efisien persona + tool guidance**

```python
SYSTEM_PROMPT = """Anda adalah asisten Customer Service AI untuk PT Efisien Integrasi
Indonesia (efisien.id), sebuah partner transformasi digital. Layanan kami: ERP & Sistem
Enterprise, AI & Machine Learning, Industrial Computer Vision, Chatbot & Conversational AI,
IoT & Embedded Systems, Data Analytics & Business Intelligence, serta Web & Mobile App
Development.

Peran Anda:
- Menjawab pertanyaan calon klien maupun klien yang sudah ada dengan ramah dan profesional.
- Selalu menjawab dalam Bahasa Indonesia, singkat, jelas, dan membantu.

Anda memiliki tool `search_knowledge_base`. Untuk SETIAP pertanyaan tentang perusahaan
(layanan, harga, profil, portofolio, kontak, atau FAQ), Anda WAJIB memanggil
`search_knowledge_base` terlebih dahulu, lalu menjawab HANYA berdasarkan hasil yang
dikembalikan. Jangan mengarang fakta. Jika hasil pencarian kosong atau tidak relevan,
katakan dengan jujur dan tawarkan untuk menghubungkan dengan tim kami.
"""
```

- [ ] **Step 2: Update `app/api/chat.py` to provide and pass a Retriever**

Full file:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.orchestrator import handle_chat
from app.db import get_session
from app.llm.base import LLMClient
from app.llm.gemini import GeminiLLM
from app.rag.embeddings import GeminiEmbedder
from app.rag.retriever import Retriever
from app.rag.store import ChromaStore
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


def get_llm() -> LLMClient:
    return GeminiLLM()


def get_retriever() -> Retriever:
    return Retriever(ChromaStore.persistent(), GeminiEmbedder())


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    session: Session = Depends(get_session),
    llm: LLMClient = Depends(get_llm),
    retriever: Retriever = Depends(get_retriever),
) -> ChatResponse:
    reply, user = handle_chat(
        session,
        llm,
        retriever,
        message=req.message,
        name=req.name,
        phone=req.phone,
        email=req.email,
    )
    return ChatResponse(reply=reply, user_id=user.id)
```

- [ ] **Step 3: Replace `tests/test_chat_api.py` (override retriever + add RAG e2e test)**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chat import get_llm, get_retriever
from app.db import get_session
from app.llm.base import LLMResponse, ToolCall
from app.llm.fake import FakeLLM
from app.main import app
from app.models.base import Base
from app.models.user import User  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.rag.embeddings import FakeEmbedder
from app.rag.retriever import Retriever
from app.rag.store import ChromaStore


class _EmptyRetriever:
    def search(self, query, k=4):
        return []


@pytest.fixture
def build_client():
    def _build(llm, retriever):
        engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(engine)
        TestSession = sessionmaker(bind=engine, expire_on_commit=False)

        def override_session():
            with TestSession() as s:
                yield s

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_llm] = lambda: llm
        app.dependency_overrides[get_retriever] = lambda: retriever
        return TestClient(app)

    yield _build
    app.dependency_overrides.clear()


def test_chat_endpoint_returns_reply(build_client):
    client = build_client(FakeLLM(reply="Halo dari AI"), _EmptyRetriever())
    resp = client.post("/chat", json={"message": "hai", "phone": "0811"})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "Halo dari AI"


def test_chat_endpoint_requires_identity(build_client):
    client = build_client(FakeLLM(reply="x"), _EmptyRetriever())
    assert client.post("/chat", json={"message": "hai"}).status_code == 422


def test_health_endpoint(build_client):
    client = build_client(FakeLLM(reply="x"), _EmptyRetriever())
    assert client.get("/health").json() == {"status": "ok"}


def test_faq_flow_uses_rag(build_client):
    # Seed an in-memory knowledge base.
    store = ChromaStore.ephemeral()
    emb = FakeEmbedder()
    store.reset()
    docs = ["Layanan kami: ERP, AI, Computer Vision.", "Kontak via WhatsApp."]
    store.add(
        ids=["0", "1"],
        embeddings=emb.embed_documents(docs),
        documents=docs,
        metadatas=[{"source": "profile.txt"}, {"source": "profile.txt"}],
    )
    retriever = Retriever(store, emb)

    # LLM: turn 1 calls the tool, turn 2 answers from the retrieved text.
    scripted = [
        LLMResponse(tool_calls=[ToolCall(name="search_knowledge_base", args={"query": "layanan"})]),
        LLMResponse(text="Layanan kami: ERP, AI, Computer Vision."),
    ]
    client = build_client(FakeLLM(responses=scripted), retriever)

    resp = client.post("/chat", json={"message": "apa saja layanan?", "phone": "0811"})
    assert resp.status_code == 200
    assert "ERP" in resp.json()["reply"]
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all tests pass (Sprint 1 + Sprint 2 tasks 2–10).

- [ ] **Step 5: Commit**

```bash
git add app/agent/prompts.py app/api/chat.py tests/test_chat_api.py
git commit -m "feat: Efisien persona + RAG tool wiring in /chat with e2e FAQ test"
```

---

### Task 11: Manual smoke test (ingest + live FAQ)

Requires a real `GEMINI_API_KEY` in `.env` and `data/docs/*.txt` present.

- [ ] **Step 1: Build the knowledge base index**

Run: `uv run python scripts/ingest_docs.py`
Expected: prints e.g. `1 file, N chunk, tersimpan ke data/chroma/`. A `data/chroma/` directory is created.

- [ ] **Step 2: Start the server**

Run: `uv run uvicorn app.main:app --port 8000`
Expected: startup complete on port 8000.

- [ ] **Step 3: Ask a FAQ and confirm a grounded, tool-backed answer**

Run:
```bash
curl -s -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"message":"Apa saja layanan PT Efisien?","name":"Budi","phone":"08123456789"}'
```
Expected: a JSON `reply` in Indonesian listing Efisien's real services (ERP, AI/ML, Computer Vision, etc.) drawn from `profile.txt` — not the old "Maju Digital" list.

- [ ] **Step 4: Confirm grounding (negative check)**

Ask something not in the docs, e.g. `{"message":"Berapa jumlah karyawan Efisien?","phone":"0811"}`.
Expected: the AI says it doesn't have that info / offers human handoff, rather than inventing a number.

- [ ] **Step 5: Stop the server**

Press Ctrl+C (or `pkill -f "uvicorn app.main:app"`).

---

## Sprint 2 Done When
- `uv run pytest` is green (Sprint 1 + all Sprint 2 tests).
- `scripts/ingest_docs.py` builds a Chroma index from `data/docs/*.txt`.
- A live FAQ question is answered by the agent calling `search_knowledge_base` and grounding
  its reply in retrieved chunks (verified with real Gemini), as PT Efisien Integrasi Indonesia.
- The tool-calling loop + tool-aware `LLMClient` + tools registry are in place for Sprint 3.

## Self-Review Notes
- **Spec coverage:** ingestion (§5)→Task 5; retrieval (§6)→Task 6; tool types (§7.1)→Task 7;
  tools registry (§7.2)→Task 8; orchestrator loop (§7.3)→Task 9; GeminiLLM function-calling
  (§7.4)→Task 7; FakeLLM scriptable (§7.5)→Task 7; system prompt + identity (§7.6)→Task 10;
  error handling (§8)→Tasks 8 (dispatch try/except), 6/Task9 (empty index, max-iter); testing
  (§9)→Tasks 2–10; embeddings/store decisions (§2)→Tasks 1–3. No gaps.
- **Identity:** `search_knowledge_base`, `Retriever.search(query,k)`, `ChromaStore` methods,
  `LLMResponse`/`ToolCall`/`ChatMessage`, `handle_chat(session, llm, retriever, *, ...)` are
  consistent across all tasks that reference them.
