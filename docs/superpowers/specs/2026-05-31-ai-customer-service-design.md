# AI Customer Service for PT Maju Digital — Design Spec

**Date:** 2026-05-31
**Status:** Approved (design phase)

## 1. Background & Goal

PT Maju Digital is a software house offering Website, Mobile App, ERP, HRIS, POS (Sistem Kasir), and custom-system development. Today all client communication is manual (sales + CS), causing slow responses, repeated questions, lost leads, double-booked meetings, and late support tickets.

We are building an **AI Customer Service agent** that automatically:

- Answers company FAQs (grounded in company documents via RAG)
- Qualifies leads by gathering client requirements
- Creates leads in the CRM
- Schedules meetings
- Checks project status
- Creates support tickets
- Remembers clients across conversations
- Hands off to a human when needed

**Intent:** A learning/portfolio build that will move to production soon. Therefore: clean, demonstrable, end-to-end flows now, with external integrations behind adapter interfaces so real services swap in later without reworking the agent.

### Actors
- **Prospective client** — "I want a POS app", "How much is a website?", "I'd like a consultation".
- **Existing client** — "What's my project status?", "I can't log in", "Is my proposal ready?".
- **Sales** — receives leads from the AI.
- **Project Manager** — receives gathered requirements / proposals.
- **Developer** — receives support tickets.

## 2. Tech Stack (locked)

- **Backend:** Python + FastAPI
- **LLM:** Google **Gemini Flash**, behind a thin provider interface (swappable later)
- **Embeddings:** Gemini `text-embedding-004`
- **RAG vector store:** **Chroma**
- **Relational DB:** **PostgreSQL** via SQLAlchemy + Alembic
- **Channel:** Web chat API + simple UI now; **channel-agnostic core** so a WhatsApp adapter can be added later
- **User identity:** lightweight — match/create a `User` by phone or email (no passwords)
- **External integrations** (CRM, calendar, email/notifications): implemented against our own DB / console now, **behind adapter interfaces** (HubSpot, Google Calendar, SMTP/WhatsApp drop in later)

## 3. Architecture

The agent uses a **single tool-calling agent loop** (Approach A). All real logic lives in a tested **service + tool layer**, not in brittle prompt steps.

```
[Web chat UI]
     │  POST /chat {user_ref, message}
     ▼
[FastAPI app]
     ├─ Channel adapter (web)        ← WhatsApp adapter slots in here later
     ▼
[Agent orchestrator]  ── single tool-calling loop
     │ 1. resolve User (phone/email)
     │ 2. load memory (client_facts) + recent messages
     │ 3. build context (system prompt + memory + history + message)
     │ 4. call Gemini Flash with tools registered
     │ 5. if tool calls → execute via Tool layer → feed back → loop (max 6)
     │ 6. final text → persist messages → return reply
     ├──────────────┬───────────────┬──────────────┐
     ▼              ▼               ▼              ▼
[LLM client]   [Tool layer]    [RAG service]   [Memory service]
 (Gemini,      (thin wrappers   (Chroma +       (conversation
  swappable)    over services)   embeddings)     store + facts)
     │
     ▼
[Service layer]  ── business logic, pure & testable
 Lead · Meeting · Ticket · Project · Notification · Proposal · Memory
     │
     ▼
[Repositories]  ── SQLAlchemy data access
     ▼
[PostgreSQL]                         [Chroma]
```

**Layering rule:** agent → tools → services → repositories → DB. The agent never touches the DB directly. External integrations live behind adapter interfaces.

### Project Structure
```
app/
  main.py                 # FastAPI entrypoint
  api/                    # routes: /chat, /health, admin
  channels/               # web adapter (whatsapp later)
  agent/
    orchestrator.py       # the tool-calling loop
    prompts.py            # system prompt
    tools.py              # tool definitions + dispatch
  llm/                    # provider interface + gemini impl
  rag/                    # ingestion + retrieval (Chroma)
  services/               # lead, meeting, ticket, project, notification, proposal, memory
  integrations/           # calendar, email, crm adapters (mock + interface)
  repositories/           # SQLAlchemy data access
  models/                 # ORM models + Pydantic schemas
  db.py                   # session/engine
data/docs/                # company PDFs for RAG
migrations/               # Alembic
tests/
scripts/ingest_docs.py    # build the Chroma index
```

## 4. Data Model (PostgreSQL)

Fields beyond the original brief are marked ➕.

**`user`** — a person chatting (prospect or existing client)
- `id`, `name`, `phone`, `email`, `created_at`, ➕ `last_seen_at`
- Identity: match on phone **or** email; create if new.

**`message`** — every conversation turn (the brief's "Conversation")
- `id`, `user_id` → user, `role` (`user`|`assistant`|`tool`), `content`, ➕ `tool_name`, `created_at`

**`client_fact`** ➕ — durable long-term memory
- `id`, `user_id`, `key`, `value`, `created_at`

**`lead`** — a qualified prospect requirement
- `id`, `user_id`, `project_type`, ➕ `platform`, ➕ `requirements` (JSON), `budget`, `status` (`new`|`qualified`|`handed_off`), ➕ `proposal` (JSON, nullable), `created_at`

**`meeting`** — a booked consultation
- `id`, `lead_id` → lead, `meeting_time`, `meeting_link`, ➕ `status` (`scheduled`|`cancelled`), `created_at`
- Available slots are **computed** by the calendar adapter (free time minus booked meetings); no slots table.

**`project`** — an existing client's project
- `id`, `client_id` → user, ➕ `name`, ➕ `type`, `progress` (0–100), `status`, ➕ `details` (JSON, e.g. `{backend:"done", frontend:80, testing:"in progress"}`), `created_at`

**`ticket`** — a support/bug report
- `id`, `project_id` → project, ➕ `user_id` → user, ➕ `category` (`bug`|`feature`|`question`), `priority` (`low`|`med`|`high`), `status` (`open`|`assigned`|`closed`), `description`, ➕ `assigned_developer`, `created_at`

**`notification`** ➕ — outbound alerts to staff
- `id`, `target_role` (`sales`|`manager`|`developer`), `payload` (JSON), `reason`, `status` (`pending`|`sent`), `created_at`

**Relationships:** `user 1─* message`, `user 1─* client_fact`, `user 1─* lead`, `lead 1─* meeting`, `user(client) 1─* project`, `project 1─* ticket`.

## 5. Agent Loop, Tools & RAG

### Agent loop (`agent/orchestrator.py`)
1. Resolve `User` from `{user_ref, message}`.
2. Assemble context: system prompt + the user's `client_fact`s + last ~15 `message` rows + new message.
3. Call Gemini Flash with all tools registered (function calling).
4. Tool calls → dispatch via Tool layer → append results → call again. **Max-iterations guard (6).**
5. Final text → persist user message, tool messages, assistant reply → return.

### System prompt (`agent/prompts.py`)
Defines: persona (PT Maju Digital's Indonesian-speaking CS assistant), company services, tone, when to call each tool, lead-qualification flow, and handoff rules.

### Tools (`agent/tools.py` — thin wrappers; logic in services)

| Tool | Backed by | Feature |
|---|---|---|
| `search_knowledge_base(query)` ➕ | RAG service (Chroma) | 1 FAQ |
| `create_lead(...)` / `get_lead(user_ref)` | Lead service | 2,3 |
| `get_available_slots(date_range)` | Calendar adapter | 4 |
| `create_meeting(lead_id, slot)` | Meeting service | 4 |
| `send_invitation(meeting_id)` | Email adapter | 4 |
| `get_project_status(client_ref, project?)` | Project service | 5 |
| `create_ticket(user_ref, product, description)` | Ticket service (auto-classifies category+priority via LLM) | 6 |
| `assign_developer(ticket_id)` | Ticket service + Notification | 6 |
| `generate_proposal(lead_id)` | Proposal service (LLM structured output) | 7 |
| `notify_sales(reason, ctx)` / `notify_manager(reason, ctx)` | Notification service | 8 |
| `remember_fact(key, value)` ➕ | Memory service | 9 |

The 11 required tools (`createLead`, `getLead`, `createMeeting`, `getAvailableSlots`, `sendInvitation`, `createTicket`, `assignDeveloper`, `getProjectStatus`, `generateProposal`, `notifySales`, `notifyManager`) are all present; `search_knowledge_base` and `remember_fact` are added support tools for the FAQ and memory features.

**Lead qualification (Feature 2)** is conversational, not a tool: the prompt guides the agent to gather project_type → platform → users/budget, then call `create_lead`. Gemini structured output produces clean JSON.

### RAG (`rag/` + `scripts/ingest_docs.py`)
- **Ingestion (offline):** load PDFs from `data/docs/` (`company_profile`, `faq`, `pricing`, `services`, `portfolio`) → chunk (~500–800 tokens, overlap) → embed with Gemini → store in Chroma with `{source}` metadata.
- **Retrieval (`search_knowledge_base`):** embed query → top-k similarity search → return chunks + sources. Agent answers grounded in chunks and can cite the source doc.

### Memory (Feature 9)
- *Short-term:* recent `message` rows in context.
- *Long-term:* `client_fact` rows loaded each turn; agent writes new ones via `remember_fact`.
- *Cross-day:* facts + messages persist keyed to the `User` (found by phone/email), so they reload on a later day.

### Proposal (Feature 7)
`generate_proposal(lead_id)` uses the LLM with structured output over the lead's requirements to produce **scope, timeline estimate, cost estimate, deliverables**. Returned in chat and stored in `lead.proposal`.

## 6. Error Handling

- **Tool dispatch** wraps each tool in try/except, returns structured `{error}` to the model so it can recover or hand off — never hard-crashes the chat.
- **Tool args** validated with Pydantic; invalid args returned as a correction prompt.
- **DB errors** → rollback + friendly "maaf, sedang ada gangguan" message.
- **LLM provider failures** → retry with backoff, then apologetic fallback + optional handoff.
- **Max-iteration guard hit** → stop, apologize, trigger handoff.
- **Out-of-scope / low-confidence / frustration** → human handoff instead of hallucinating.

## 7. Human Handoff (Feature 8)

Triggers (in prompt + guardrail): explicit request for a person, contract negotiation, payment/billing complaints, repeated tool failure. Action: call `notify_sales`/`notify_manager` (writes a `notification` row + console log now; email/WhatsApp later), tell the user a human will follow up. Full conversation stays logged for staff context.

## 8. Testing Strategy (TDD)

- **Services & repositories:** unit tests against a test Postgres (transactional rollback) — bulk of coverage.
- **Tool layer:** tests with mocked services.
- **Orchestrator loop:** tested with a **fake LLM** returning scripted tool calls — full loop, deterministic, no API cost.
- **RAG:** retrieval test over a small sample doc set (asserts correct chunk/source).
- **End-to-end:** a few `/chat` tests with the stubbed LLM, one per DOD item, as living acceptance checks.

## 9. Build Order (7 vertical-slice sprints)

| Sprint | Deliverable |
|---|---|
| **1** | Skeleton: FastAPI, Postgres+Alembic, `User`/`message`, `/chat` + Gemini chat loop (no tools), minimal web UI |
| **2** | RAG: ingest PDFs → Chroma, `search_knowledge_base` tool (Feature 1) |
| **3** | Lead qualification dialogue + `create_lead`/`get_lead` (Features 2,3) |
| **4** | Meeting booking: `get_available_slots`, `create_meeting`, `send_invitation` (Feature 4) |
| **5** | `get_project_status`, `create_ticket`, `assign_developer` (Features 5,6) |
| **6** | Memory (`client_fact`, `remember_fact`) + handoff (`notify_sales`/`notify_manager`) (Features 8,9) |
| **7** | `generate_proposal` + end-to-end polish & full workflow (Feature 7) |

## 10. Definition of Done

The system is complete when the AI can:
- ✅ Answer company FAQs
- ✅ Access the knowledge base via RAG
- ✅ Qualify client requirements
- ✅ Save leads to the database
- ✅ Schedule meetings
- ✅ Check project status
- ✅ Create support tickets
- ✅ Remember previous conversations
- ✅ Hand off to a human when needed
- ✅ Persist all activity to the database
