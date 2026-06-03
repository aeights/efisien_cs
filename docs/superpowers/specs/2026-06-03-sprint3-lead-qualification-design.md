# Sprint 3 — Lead Qualification + CRM Design Spec

**Date:** 2026-06-03
**Status:** Approved (design phase)
**Builds on:** Sprint 2 (RAG FAQ + tool-calling loop). Reuses the tool-calling foundation; adds the first **database-writing** tools.

## 1. Goal

Implement **Feature 2 (Lead Qualification)** and **Feature 3 (CRM / save lead)**:

- The agent gathers a prospect's project requirements through natural dialogue.
- It persists the result as a `lead` row via two new tools: `create_lead` and `get_lead`.

This is the first sprint where a tool **writes to PostgreSQL**, so it also establishes how
the dispatcher receives DB/context dependencies (session + current user).

## 2. Decisions (locked)

- **No service layer yet (lean).** Tools in `dispatch` call `LeadRepository` directly, matching
  the Sprint 1–2 pattern. A `services/` layer is deferred until real business logic appears
  (e.g. Sprint 7 proposal). YAGNI.
- **`user_id` is injected, never an LLM argument.** The orchestrator already resolves the
  current `User` (by phone/email). `create_lead`/`get_lead` operate on that user; the LLM cannot
  pass or spoof a user identity.
- **`requirements` and `budget` are free text** (strings). `requirements` is stored as JSON
  `{"text": "..."}` so it can grow into a structured shape later without a migration. `budget`
  is a flexible string (e.g. "20–30 juta", "belum ada").
- **Upsert on the open lead.** `create_lead` updates the user's latest `status="new"` lead if one
  exists; otherwise it creates a new one. This avoids duplicate leads across the multi-turn
  qualification dialogue while keeping `user 1─* lead` (a user may still accumulate several leads
  over time once earlier ones leave `"new"`).
- **`get_lead` returns the latest lead** for the current user (single object, not a list).
- **Status stays `"new"` in Sprint 3.** The enum (`new`/`qualified`/`handed_off`) is provisioned,
  but transitions to `qualified`/`handed_off` are deferred (handoff = Sprint 6).
- **`proposal` column is provisioned but unused** until Sprint 7 (always `NULL` now).

## 3. Data Model — new `leads` table

`app/models/lead.py`:

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `user_id` | Integer FK → `users.id`, index | owning user |
| `project_type` | String(120), nullable | e.g. "POS", "Website", "Mobile App" |
| `platform` | String(120), nullable | e.g. "Web", "Android", "Web + iOS" |
| `requirements` | JSON, nullable | free-text summary wrapped as `{"text": "..."}` |
| `budget` | String(120), nullable | flexible string |
| `status` | String(16), default `"new"` | logical enum: `new`/`qualified`/`handed_off` |
| `proposal` | JSON, nullable | Sprint 7; always `NULL` now |
| `created_at` | DateTime(timezone=True) | `server_default=func.now()` |

- Relationship: `user 1─* lead`.
- Register the model in `alembic/env.py`, run `alembic revision --autogenerate`, **review the
  generated migration** before `upgrade` (the Sprint 1 lesson: autogenerate can emit unwanted
  drops).

## 4. Repository — `app/repositories/lead_repo.py`

```python
class LeadRepository:
    def __init__(self, session): ...

    def get_latest(self, user_id) -> Lead | None:
        # newest lead for the user (order by id desc, limit 1)

    def get_open(self, user_id) -> Lead | None:
        # newest lead with status == "new" (the upsert target)

    def upsert(self, user_id, *, project_type=None, platform=None,
               requirements=None, budget=None) -> Lead:
        # if an open ("new") lead exists: update only the provided (non-None) fields
        # else: create a new lead with status "new"
        # flush() to obtain id; commit stays in the orchestrator
```

- Partial update: `None` arguments do **not** overwrite existing values, so an early turn can set
  `project_type` and a later turn can add `budget` without clobbering the first.
- `requirements` argument is the raw text; the repository wraps/stores it as `{"text": ...}`.

## 5. Tools + dispatch wiring

`dispatch` now needs DB access and the current user. New signature:

```python
def dispatch(tool_call, *, retriever, session, user) -> str
```

The orchestrator passes `session` and the resolved `user` into every `dispatch` call. `api/chat.py`
needs no new dependency (it already injects `session`); the orchestrator forwards them.

New entries in `TOOL_SPECS`:

| Tool | Args (LLM-provided) | Backed by | Returns |
|---|---|---|---|
| `create_lead` | `project_type?`, `platform?`, `requirements?`, `budget?` (all optional strings) | `LeadRepository.upsert` with injected `user_id` | `{"lead_id", "status", "project_type", "platform", "budget"}` |
| `get_lead` | (none) | `LeadRepository.get_latest(user_id)` | lead fields, or `{"result": "Belum ada lead."}` |

- Both wrapped in `try/except` → `{"error": ...}` (existing pattern). `ensure_ascii=False`.
- Unknown-tool branch already returns a handled error.

## 6. Qualification flow — `app/agent/prompts.py`

Lead qualification is **dialogue, not a tool**. Add to `SYSTEM_PROMPT`:

- When a prospect shows interest in a project, gather information gradually and warmly (don't
  interrogate): **project type → platform → key requirements → budget estimate**.
- Once there is enough information, call `create_lead`. It is fine to call it again as more detail
  arrives — the upsert updates the same open lead.
- Use `get_lead` when the user asks about their earlier request / summary.
- Keep the existing rule: still **must** call `search_knowledge_base` for questions about
  services/pricing/profile/FAQ, answering only from results.

## 7. Error Handling

- Each tool wrapped in `try/except` → `{"error": ...}`; chat never hard-crashes.
- All lead fields nullable, so missing args are safe; the agent decides when info is sufficient.
- DB commit remains a single `session.commit()` at the end of the orchestrator turn.

## 8. Testing (TDD; in-memory SQLite, no real API)

- **`test_lead_repo.py`** — upsert creates new; upsert updates the existing `"new"` lead (partial,
  non-None only); `get_latest` / `get_open` behavior.
- **`test_tools.py`** (extend) — `create_lead` injects the correct `user_id`; `get_lead` empty vs
  present; error path.
- **`test_orchestrator.py`** (extend) — scripted `FakeLLM`: turn 1 calls `create_lead`, turn 2
  returns text → lead persisted in DB, final reply correct.
- **`test_chat_api.py`** (extend) — end-to-end `/chat` for a short qualification flow (FakeLLM) →
  lead exists in DB.
- **Manual smoke test:** live qualification dialogue with real Gemini; confirm a `lead` row is
  written and `get_lead` recalls it.

## 9. Build Order (vertical slice)

1. `Lead` model + Alembic migration (register in `env.py`, autogenerate, **review**, upgrade).
2. `LeadRepository` + tests.
3. `create_lead`/`get_lead` tools + change `dispatch` signature + wire orchestrator & `api/chat.py` + tests.
4. Update `SYSTEM_PROMPT` (qualification flow).
5. Orchestrator + e2e `/chat` tests.
6. Live smoke test, then finish the development branch.

## 10. Definition of Done (Sprint 3)

- A `leads` table exists (via migration) with the columns above.
- The agent gathers requirements conversationally and calls `create_lead`, persisting a `lead`
  row tied to the current user; calling it again upserts the same open lead.
- `get_lead` returns the user's latest lead.
- `user_id` is injected from context, never taken from LLM arguments.
- All tests green (Sprint 1 + Sprint 2 + new Sprint 3 tests).
- Verified live with real Gemini.
