# Efisien CS — AI Customer Service Agent

An AI Customer Service agent for **PT Efisien Integrasi Indonesia**, a digital-transformation software house. Prospective and existing clients chat in natural language (Bahasa Indonesia); a **Google Gemini**-powered agent answers grounded company questions, qualifies sales leads, drafts proposals, books consultation meetings, checks project status, files support tickets, remembers clients across conversations, and escalates to a human when needed — persisting every action to a database.

Built backend-first with FastAPI, a single tool-calling agent loop, Retrieval-Augmented Generation (RAG), and a clean, fully-tested, provider-agnostic architecture.

---

## Table of Contents
- [What it does](#what-it-does)
- [Key features](#key-features)
- [How it works (agent workflow)](#how-it-works-agent-workflow)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Data model](#data-model)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Testing](#testing)
- [Engineering practices](#engineering-practices)
- [For your CV / resume](#for-your-cv--resume)

---

## What it does

A single chat endpoint (`POST /chat`) drives an autonomous agent that decides, per message, which capabilities to invoke. The agent serves two audiences:

- **Prospective clients** — answer FAQs from official company documents, gather requirements, save a lead, generate a proposal, and schedule a consultation.
- **Existing clients** — report project status, open and route support tickets, and reach a human for billing/contract matters.

Everything the agent does is backed by tested business logic and stored in PostgreSQL — not improvised in the prompt.

## Key features

| # | Feature | How |
|---|---------|-----|
| 1 | **FAQ answering (RAG)** | Retrieves chunks of company documents from a Chroma vector store and answers grounded in them — no hallucinated facts. |
| 2 | **Lead qualification** | Conversationally gathers project type, platform, requirements, and budget. |
| 3 | **CRM lead capture** | Persists/updates leads (`create_lead` / `get_lead`) with idempotent upsert. |
| 4 | **Meeting booking** | Computes free working-hour slots (WIB), books a consultation, and "sends" an invitation (`get_available_slots` / `create_meeting` / `send_invitation`). |
| 5 | **Project status** | Existing clients query progress of their projects (`get_project_status`). |
| 6 | **Support tickets** | Creates classified tickets (bug/feature/question, priority) and assigns them to the dev team (`create_ticket` / `assign_developer`). |
| 7 | **Proposal generation** | Produces a structured proposal (scope, timeline, cost, deliverables) and marks the lead *qualified* (`generate_proposal`). |
| 8 | **Long-term memory** | Remembers durable client facts (name, company, preferences) across conversations and reloads them into context (`remember_fact`). |
| 9 | **Human handoff** | Escalates to sales or a manager with a logged notification (`notify_sales` / `notify_manager`). |

**13 tools** in total, all routed through one agent loop.

## How it works (agent workflow)

```
Browser (chat UI)
   │  POST /chat { message, name, phone }
   ▼
FastAPI route ── validates payload, injects dependencies (DB, LLM, retriever, adapters)
   ▼
Agent orchestrator ── single tool-calling loop
   1. Resolve/create the user (by phone or email)
   2. Load long-term memory (client_facts) → inject into the system prompt
   3. Load recent conversation history
   4. Call Gemini with the system prompt + history + all 13 tool schemas
   5. If the model requests tools → dispatch each, feed results back → loop (max 6)
   6. On a final text answer → persist user + assistant messages → return reply
   ▼
Tool dispatch ── thin handlers over repositories & integration adapters
   ▼
PostgreSQL (relational state)        Chroma (RAG vector store)
```

**Design principle — the LLM supplies content, the code enforces identity & invariants.** The model fills tool arguments (requirements, chosen slot, ticket description, proposal fields), but user identity and foreign keys are injected from the conversation context, never trusted from the model. Tools validate inputs (enum values, slot availability) before writing, and the prompt forbids claiming success before a tool actually confirms it.

## Architecture

- **Single tool-calling agent loop** — one orchestrator turns model tool-calls into real actions and feeds results back until a final answer, with a max-iteration guard.
- **RAG pipeline** — offline ingestion (load → section-aware chunking → embed → store in Chroma); online retrieval embeds the query and returns the top matches with sources.
- **Provider-agnostic interfaces** — `LLMClient`, `Retriever`, and adapter ABCs (`CalendarAdapter`, `EmailAdapter`) decouple the agent from Gemini / Google Calendar / SMTP. Real implementations drop in for production; in-memory fakes drive the tests.
- **Repository pattern** — all SQL lives in repositories; the agent never touches the database directly.
- **Dependency injection** — FastAPI `Depends` wires real services in production and overrides them with fakes in tests.

## Tech stack

- **Language/runtime:** Python 3.14, [`uv`](https://github.com/astral-sh/uv) package manager
- **Web:** FastAPI + Uvicorn
- **LLM:** Google Gemini (`google-genai`) behind a thin provider interface
- **RAG:** Chroma vector store + Gemini embeddings, section-aware chunking
- **Database:** PostgreSQL via SQLAlchemy 2.0 (typed `Mapped` models) + Alembic migrations
- **Testing:** pytest with in-memory SQLite + scriptable fakes
- **Packaging/Run:** Docker + Docker Compose (app + Postgres, one command)

## Data model

Eight tables (`users`, `messages`, `leads`, `meetings`, `projects`, `tickets`, `client_facts`, `notifications`) evolved across five Alembic migrations. Highlights:

- `users` identified lightly by phone/email (no passwords).
- `leads` carry requirements (JSON) and a generated `proposal` (JSON).
- `tickets` require an owner (`user_id`) but optionally link a `project_id`.
- `client_facts` use a `(user_id, key)` unique constraint to support upsert-based memory.

## Project structure

```
app/
  main.py            # FastAPI app + static chat UI
  api/chat.py        # /chat and /health routes
  agent/             # orchestrator (loop), prompts (system prompt), tools (13 tools + dispatch)
  llm/               # provider interface + Gemini impl + fake
  rag/               # embeddings, Chroma store, chunking, ingest, retriever
  integrations/      # calendar & email adapters (local/console now, real later)
  repositories/      # SQLAlchemy data access (one per aggregate)
  models/            # ORM models (8 tables)
  config.py / db.py  # settings + session
alembic/             # migrations
scripts/             # ingest_docs.py, seed_projects.py
static/index.html    # minimal chat UI
tests/               # 84 tests (unit, tool, orchestrator, end-to-end)
```

## Getting started

### Option A — Docker (recommended, one command)

Requires Docker + Docker Compose, and a `.env` (copy from `.env.example`, set `GEMINI_API_KEY`).

```bash
docker compose up --build
# → migrations run, RAG index builds once, server starts
# open http://localhost:8000
```

Details and helper commands: [`docs/menjalankan-dengan-docker.md`](docs/menjalankan-dengan-docker.md).

### Option B — Local

Requires Python 3.14, `uv`, and a running PostgreSQL.

```bash
uv sync                                  # install dependencies
cp .env.example .env                     # then set GEMINI_API_KEY (and DATABASE_URL)
uv run alembic upgrade head              # create tables
uv run python scripts/ingest_docs.py     # build the RAG index
uv run uvicorn app.main:app --reload     # serve at http://localhost:8000
```

## Testing

```bash
uv run pytest          # 84 tests, all green
```

Tests run without any real API calls or external services: the LLM, embeddings, calendar, and email are replaced with deterministic fakes, and the database is in-memory SQLite. Coverage spans repositories, the tool dispatcher, the full orchestrator loop (with scripted tool-calls), and end-to-end `/chat` acceptance flows — including a full-journey test (FAQ → lead → proposal → booking).

## Engineering practices

- **Vertical-slice delivery** — built in 7 sprints, each shipping a working, tested feature end-to-end.
- **Spec → plan → TDD execution** — every sprint went through a written design spec, a bite-sized implementation plan, and test-first implementation.
- **Live smoke testing** — each feature verified against the real Gemini model; prompt and code hardening (e.g. anti-hallucination rules, empty-reply guard) came from real findings.
- **Frequent, scoped commits** and clean migration history.

---

## For your CV / resume

**One-line:**
> Designed and built an AI Customer Service agent (FastAPI + Google Gemini) that autonomously handles FAQs, lead qualification, proposal generation, meeting booking, support tickets, and human handoff — backed by RAG, PostgreSQL, and a 13-tool agent loop with 84 automated tests.

**Resume bullets (English):**
- Built an LLM agent (Google Gemini) with a **single tool-calling loop** orchestrating **13 tools** across sales, scheduling, support, memory, and human-handoff workflows.
- Implemented **Retrieval-Augmented Generation** (Chroma + embeddings, section-aware chunking) to ground answers in company documents and eliminate hallucinated facts.
- Designed a **provider-agnostic architecture** (LLM/RAG/calendar/email behind interfaces + repository pattern + dependency injection), enabling **84 fast, free tests** with in-memory fakes and an in-memory database.
- Modeled **8 PostgreSQL tables** with SQLAlchemy 2.0 and **5 Alembic migrations**; enforced data integrity (injected identity, validated tool inputs, upsert-based long-term memory).
- Delivered in **7 test-driven vertical-slice sprints** (spec → plan → TDD → live smoke test → merge), and **containerized with Docker Compose** for one-command setup.

**Versi Bahasa Indonesia (ringkas):**
> Merancang dan membangun agen AI Customer Service (FastAPI + Google Gemini) yang secara otomatis menangani FAQ, kualifikasi lead, pembuatan proposal, penjadwalan meeting, tiket support, memori jangka panjang, dan eskalasi ke manusia — didukung RAG, PostgreSQL, dan agent loop berisi 13 tool dengan 84 test otomatis. Dibangun dalam 7 sprint berbasis TDD dengan arsitektur provider-agnostic dan dikemas dengan Docker Compose.

---

> **Status:** Portfolio / production-oriented build. External integrations (calendar, email, notifications) run against local/console implementations behind adapter interfaces, ready to be swapped for real services (Google Calendar, SMTP/WhatsApp, Slack) without changing the agent.
