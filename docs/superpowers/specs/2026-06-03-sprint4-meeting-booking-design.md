# Sprint 4 — Meeting Booking Design Spec

**Date:** 2026-06-03
**Status:** Approved (design phase)
**Builds on:** Sprint 3 (lead qualification + CRM, injected-user tool pattern). Reuses the tool-calling loop; introduces the **adapter pattern** for external integrations.

## 1. Goal

Implement **Feature 4 (Meeting Booking)** with three tools — `get_available_slots`,
`create_meeting`, `send_invitation` — and a new `meetings` table. This is the first sprint
where external integrations (calendar, email) live behind **adapter interfaces**, so real
services (Google Calendar, SMTP) can swap in later without touching the agent.

## 2. Decisions (locked)

- **Adapter pattern.** New `app/integrations/` package: `CalendarAdapter` (ABC) + `LocalCalendar`,
  and `EmailAdapter` (ABC) + `ConsoleEmail`. Adapters are pure (no DB access); the dispatch layer
  feeds them data.
- **No slots table.** Available slots are *computed*: business-hour slots minus booked meetings.
- **Slot rules.** Mon–Fri, 09:00–16:00 start times, 1-hour slots, 7-day horizon from "now".
  Only future slots. Business hours / horizon are tunable constants.
- **Timezone Asia/Jakarta (WIB)** via `zoneinfo`. `meeting_time` stored timezone-aware. Canonical
  string exchanged with the LLM: `"YYYY-MM-DD HH:MM"` (WIB implied).
- **`now` is injected** into `LocalCalendar.available_slots(...)` for deterministic tests.
- **create_meeting links to the user's latest lead** (injected, like Sprint 3). LLM passes only the
  chosen `slot`. If the user has no lead → return a structured message telling the agent to qualify
  first. The chosen slot is **validated** against current availability (prevents double-booking /
  invalid times).
- **send_invitation takes no LLM args** — it resolves the user's latest meeting and sends to
  `user.email` or, if absent, `user.phone`, via the email adapter.
- **meeting_link** is a placeholder generated at create time: `https://meet.efisien.id/<token>`.
- **dispatch keeps keyword deps** (`retriever`, `session`, `user`, `calendar`, `email`), all
  defaulting to `None`. No context object yet (minimal churn); revisit if deps keep growing.
- **status enum** `scheduled`/`cancelled`; Sprint 4 only creates `scheduled` (cancellation deferred).

## 3. Data Model — new `meetings` table

`app/models/meeting.py`:

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `lead_id` | Integer FK → `leads.id`, index | meeting is about this lead's project |
| `meeting_time` | DateTime(timezone=True) | consultation time (WIB) |
| `meeting_link` | String(255) | placeholder link |
| `status` | String(16), default `"scheduled"` | `scheduled`/`cancelled` |
| `created_at` | DateTime(timezone=True) | `server_default=func.now()` |

- Relationship: `lead 1─* meeting`.
- Register in `alembic/env.py`; autogenerate; **review** (only `create_table('meetings')`); upgrade.

## 4. Adapters — `app/integrations/`

### `calendar.py`
```python
class CalendarAdapter(ABC):
    @abstractmethod
    def available_slots(self, booked: set[datetime], *, now: datetime) -> list[datetime]: ...

class LocalCalendar(CalendarAdapter):
    # constants: WORK_START=9, WORK_END=17 (last slot starts 16:00),
    #            SLOT_HOURS=1, HORIZON_DAYS=7, weekdays Mon-Fri
    # generate hourly business-hour datetimes for the next HORIZON_DAYS from `now`,
    # drop slots <= now and slots in `booked`, return sorted list
```

### `email.py`
```python
class EmailAdapter(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None: ...

class ConsoleEmail(EmailAdapter):
    # logs/prints "would send to <to>: <subject>"; real SMTP swaps in later
```

Adapters take no DB session. Booked times come from `MeetingRepository` and are passed in.

## 5. Repository — `app/repositories/meeting_repo.py`

```python
class MeetingRepository:
    def __init__(self, session): ...
    def scheduled_times(self) -> set[datetime]:
        # all meeting_time where status == "scheduled"
    def get_latest_for_user(self, user_id) -> Meeting | None:
        # join Meeting -> Lead, where Lead.user_id == user_id, order by Meeting.id desc
    def create(self, lead_id, meeting_time, meeting_link) -> Meeting:
        # status "scheduled"; flush(); commit stays in orchestrator
```

## 6. Tools + dispatch wiring

`dispatch(tool_call, *, retriever=None, session=None, user=None, calendar=None, email=None)`.
The orchestrator injects `calendar`/`email`; `api/chat.py` provides them via `get_calendar()` /
`get_email()` dependencies (overridable in tests).

A small module helper formats/parses the canonical slot string and the WIB timezone:
- `WIB = ZoneInfo("Asia/Jakarta")`, `now_wib()`, `fmt_slot(dt) -> "YYYY-MM-DD HH:MM"`,
  `parse_slot(s) -> datetime` (tz-aware WIB). Place these where the tools can reuse them
  (e.g. top of `tools.py` or a tiny `app/integrations/calendar.py` helper) — keep one source of truth.

| Tool | LLM args | Backed by | Returns |
|---|---|---|---|
| `get_available_slots` | (none) | `MeetingRepository.scheduled_times` + `calendar.available_slots(now=now_wib())` | `{"slots": ["YYYY-MM-DD HH:MM", ...]}` (≤ 8 nearest) |
| `create_meeting` | `slot` (string) | resolve latest lead (injected) → validate slot in current availability → `MeetingRepository.create` with generated link | `{"meeting_id","meeting_time","meeting_link","status"}` or `{"result": "belum ada lead ..."}` / `{"error": "slot tidak tersedia ..."}` |
| `send_invitation` | (none) | `MeetingRepository.get_latest_for_user` → `email.send(to=user.email or user.phone, ...)` | `{"result": "Undangan terkirim ke ..."}` or `{"result": "belum ada meeting ..."}` |

- All wrapped in `try/except` → `{"error": ...}`. `ensure_ascii=False`.
- `create_meeting` recomputes availability with `now_wib()` and checks the parsed slot is a member;
  not a member → structured error so the agent offers another slot.

## 7. Qualification/Booking flow — `app/agent/prompts.py`

Add guidance: when the user wants a consultation/meeting, ensure requirements are captured
(`create_lead` first if needed), call `get_available_slots`, offer the slots, and after the user
picks one call `create_meeting(slot=...)`, then `send_invitation`. Confirm the time + link to the
user. Keep existing FAQ and lead-qualification rules.

## 8. Error Handling

- Each tool `try/except` → `{"error": ...}`; chat never crashes.
- No lead → structured "qualify first" message. Invalid/unavailable slot → structured error.
- No meeting yet for `send_invitation` → structured message.
- DB commit remains a single `session.commit()` at end of the orchestrator turn.

## 9. Testing (TDD; in-memory SQLite, no real API)

- **`test_calendar.py`** — `LocalCalendar` with a fixed `now`: correct business-hour slots, skips
  weekends and past times, subtracts `booked`.
- **`test_email.py`** — `ConsoleEmail.send` writes to an injected sink/log (fake sink).
- **`test_meeting_repo.py`** — `create`, `scheduled_times`, `get_latest_for_user` (via the join).
- **`test_tools.py`** (extend) — `get_available_slots` (fake calendar); `create_meeting` (injects
  lead, validates slot, no-lead path); `send_invitation` (fake email); error paths.
- **`test_orchestrator.py`** (extend) — scripted loop: `get_available_slots` → `create_meeting` →
  text → meeting persisted.
- **`test_chat_api.py`** (extend) — e2e booking flow (register `Meeting` model for table creation).
- **Manual smoke test:** live booking dialogue with real Gemini; confirm a `meetings` row is written
  and the invitation is logged.

## 10. Build Order (vertical slice)

1. `Meeting` model + migration (register, autogenerate, **review**, upgrade).
2. `app/integrations/` adapters (calendar, email) + slot helpers + tests.
3. `MeetingRepository` + tests.
4. Three tools + extend `dispatch` + wire orchestrator & `api/chat.py` + tests.
5. Update `SYSTEM_PROMPT` (booking flow).
6. Orchestrator + e2e `/chat` tests.
7. Live smoke test, then finish the development branch.

## 11. Definition of Done (Sprint 4)

- A `meetings` table exists (via migration).
- `get_available_slots` returns computed business-hour slots minus booked meetings.
- `create_meeting` ties a meeting to the user's latest lead, validates the chosen slot, stores it
  with a link; `send_invitation` "sends" via the email adapter.
- Calendar and email live behind adapter interfaces (`LocalCalendar`, `ConsoleEmail`).
- `lead_id`/meeting are resolved from context, never from LLM arguments.
- All tests green (Sprints 1–3 + new Sprint 4 tests).
- Verified live with real Gemini.
