# Sprint 2 — RAG FAQ + Tool-Calling Design Spec

**Date:** 2026-05-31
**Status:** Approved (design phase)
**Builds on:** Sprint 1 chat skeleton (FastAPI + Postgres + Gemini chat loop, no tools).

## 1. Goal

Add the FAQ Assistant (Feature 1) via Retrieval-Augmented Generation, and introduce the
**tool-calling loop** into the orchestrator — the foundation every later sprint (3–7) builds on.

The AI answers company questions (services, pricing, profile, FAQ) **grounded** in the
company's own documents, retrieved from a vector store, rather than from the model's
general knowledge.

## 2. Decisions (locked)

- **Knowledge base source:** plain `.txt` files in `data/docs/` (the user already has these).
- **RAG trigger:** **tool-calling** — `search_knowledge_base` is registered as a Gemini
  function/tool; the LLM decides when to call it. (Not always-retrieve.)
- **Embeddings:** Gemini `text-embedding-004` (DOCUMENT vs QUERY task types).
- **Vector store:** Chroma, persisted at `data/chroma/` (gitignored), collection `company_docs`.
- **No new DB migration:** the `messages` table already has `tool_name` (added in Sprint 1).

## 3. Components & File Layout

```
app/
  rag/
    __init__.py
    embeddings.py      # Embedder interface + GeminiEmbedder + FakeEmbedder
    store.py           # Chroma wrapper (persistent client, collection company_docs)
    ingest.py          # read .txt -> chunk -> embed -> store (idempotent rebuild)
    retriever.py       # search(query, k) -> list of {text, source, score}
  agent/
    tools.py           # TOOL_SPECS + dispatch(tool_call, deps)
    orchestrator.py    # CHANGED: tool-calling loop
    prompts.py         # CHANGED: tell the agent about search_knowledge_base
  llm/
    base.py            # CHANGED: ToolSpec, ToolCall, LLMResponse; generate(system, messages, tools)
    gemini.py          # CHANGED: translate tools + functionCall/functionResponse
    fake.py            # CHANGED: scriptable tool-call replies
scripts/
  ingest_docs.py       # CLI entrypoint to build the index
data/docs/*.txt        # source documents (user-provided)
data/chroma/           # vector index (gitignored)
```

## 4. Data Flow (FAQ question)

```
user: "Apa saja layanan kalian?"
  -> orchestrator calls llm.generate(system, messages, tools=TOOL_SPECS)
  -> Gemini returns a ToolCall: search_knowledge_base(query="layanan")
  -> dispatch -> retriever.search: embed query -> Chroma similarity search -> chunks + sources
  -> tool result fed back into messages
  -> Gemini composes a grounded answer from the chunks
  -> final text -> persist (user msg + final assistant msg) -> return
```

**History persistence:** tool calls are *within-turn* and not replayed in later turns. The
conversation history stored/replayed remains user message + final assistant reply (as in
Sprint 1). Tool usage is logged for audit but does not bloat later-turn context.

## 5. Ingestion Pipeline (`app/rag/ingest.py` + `scripts/ingest_docs.py`)

1. **Read** all `*.txt` from `data/docs/`.
2. **Chunk:** split on blank-line paragraphs, then group paragraphs up to ~600 chars per
   chunk with ~1-paragraph overlap between consecutive chunks. Each chunk carries metadata
   `{source: "faq.txt", chunk_index: N}`.
3. **Embed:** `text-embedding-004` (task type DOCUMENT) via `Embedder.embed_documents`.
4. **Store:** upsert into Chroma collection `company_docs` (id, vector, document text, metadata).
5. **Idempotent rebuild:** each run clears the collection and rebuilds from scratch — editing
   `.txt` and re-running yields a fresh, duplicate-free index.
6. **Output:** prints a summary, e.g. `5 files, 23 chunks, stored to data/chroma/`.

## 6. RAG Retrieval (`app/rag/retriever.py`)

- `search(query, k=4) -> list[{text, source, score}]`: embed the query (task type QUERY),
  run Chroma similarity search, return top-k chunks with their source filename.
- Empty index or no relevant hits → returns an empty list; the tool reports "no relevant
  info" so the AI answers honestly / offers handoff rather than hallucinating.

## 7. Tool-Calling Design

### 7.1 New LLM types (`app/llm/base.py`)
```python
@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict          # JSON schema for the tool's arguments

@dataclass
class ToolCall:
    name: str
    args: dict

@dataclass
class LLMResponse:
    text: str | None
    tool_calls: list[ToolCall]   # empty when the model answers directly
```
`ChatMessage` is extended to represent: an `assistant` turn carrying `tool_calls`, and a
`tool` turn carrying `tool_name` + result content. `generate` becomes
`generate(system, messages, tools) -> LLMResponse`.

### 7.2 Tools registry (`app/agent/tools.py`)
- `TOOL_SPECS`: list of `ToolSpec`. Sprint 2 has one: `search_knowledge_base(query: str)`.
- `dispatch(tool_call, deps) -> str`: execute the requested tool (calls `retriever.search`),
  return the result as text to feed back to the LLM. Each tool is wrapped in try/except → on
  error returns `{"error": ...}` so the LLM can recover instead of crashing.

### 7.3 Orchestrator loop (`app/agent/orchestrator.py`)
```
messages = history + [user message]
repeat up to 6 times:
    resp = llm.generate(SYSTEM_PROMPT, messages, tools=TOOL_SPECS)
    if resp.tool_calls:
        for tc in resp.tool_calls:
            result = dispatch(tc)
            messages += [assistant(tool_call), tool(result)]
        continue            # feed tool results back to the LLM
    else:
        final = resp.text; break
persist(user message, final assistant message); return final
```
A **max-iterations guard (6)** prevents infinite loops. If the limit is reached with no final
answer → apologize (handoff comes in a later sprint).

### 7.4 GeminiLLM (`app/llm/gemini.py`)
Translate `ToolSpec` → Gemini function declarations, and translate Gemini
`functionCall`/`functionResponse` ↔ our `ToolCall`/tool messages. All Gemini-specific
translation stays in `gemini.py`; the orchestrator stays provider-agnostic.

### 7.5 FakeLLM (`app/llm/fake.py`)
Scriptable: e.g. "turn 1 → request `search_knowledge_base`, turn 2 → return text". Enables
testing the tool-calling loop without the real API.

### 7.6 System prompt (`app/agent/prompts.py`)
Updated: tell the AI it has `search_knowledge_base` and **must** use it for questions about
services/pricing/profile/FAQ, then answer from the results — never invent facts.

## 8. Error Handling

- Each tool wrapped in try/except → `{"error": ...}` back to the LLM (no chat crash).
- Empty / unbuilt Chroma index → retriever returns empty → AI answers honestly / offers handoff.
- Embedding API failure: during *ingest* the script stops with a clear message; during *query*
  the tool returns a handled error.
- Max-iteration guard → stop + apologize if the LLM keeps calling tools without answering.

## 9. Testing (TDD; SQLite + no real API)

- **Chunking** (`ingest`): sample text → correct chunk count/content, overlap, source metadata.
- **Embedder & Store:** `FakeEmbedder` (deterministic vectors, e.g. hash-based) + in-memory
  Chroma → documents in → `search` returns the most relevant chunk + source.
- **Retriever:** query → results ranked by similarity (FakeEmbedder).
- **Tool dispatch:** `dispatch(search_knowledge_base)` calls retriever & formats results;
  error path returns `{"error": ...}`.
- **Orchestrator tool-calling loop:** scriptable `FakeLLM` (turn 1 tool call, turn 2 text) →
  verify the tool runs, results feed back, final reply correct, and the max-iter guard works.
- **End-to-end `/chat`:** FakeLLM + FakeEmbedder → one full FAQ flow as the DOD acceptance check.
- **Manual smoke test:** `python scripts/ingest_docs.py` then ask a FAQ via the UI with real Gemini.

## 10. Build Order (vertical slices)

1. `Embedder` interface + `FakeEmbedder` (+ `GeminiEmbedder`)
2. Chroma store wrapper
3. Chunking + ingest pipeline + `scripts/ingest_docs.py`
4. Retriever
5. Extend `LLMClient` (new types) + scriptable `FakeLLM`
6. `GeminiLLM` function-calling support
7. `tools.py` (specs + dispatch)
8. Orchestrator tool-calling loop
9. Update system prompt + `/chat` wiring + e2e test + manual smoke test

## 11. Definition of Done (Sprint 2)

- `python scripts/ingest_docs.py` builds a Chroma index from `data/docs/*.txt`.
- The agent answers a company FAQ by calling `search_knowledge_base` and grounding its reply
  in retrieved chunks (verified live with real Gemini).
- The tool-calling loop, the extended provider-agnostic `LLMClient`, and the tools registry
  are in place — ready for Sprint 3 (lead qualification + CRM tools).
- All tests green (Sprint 1 tests + new Sprint 2 tests).
