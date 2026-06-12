# Production Integrations (Gmail SMTP + Google Calendar + WhatsApp/WAHA) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mengirim email nyata via Gmail SMTP, mengelola jadwal via Google Calendar (baca freebusy + buat event), dan menambah channel WhatsApp via WAHA sehingga klien bisa chat dengan agen lewat WhatsApp.

**Architecture:** Tiga slice independen di balik interface yang sudah ada (`EmailAdapter`, `CalendarAdapter`) + satu channel baru (`/webhook/whatsapp`). Semua di-wire lewat config env dengan fallback aman (kredensial kosong → ConsoleEmail/LocalCalendar). Implementasi nyata diuji dengan fake/mock (SMTP factory, fake Google service, fake httpx) tanpa jaringan.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy/Alembic, smtplib, google-api-python-client + google-auth, httpx, Docker Compose, WAHA (`devlikeapro/waha`).

---

## File Structure

| File | Aksi | Tanggung jawab |
|---|---|---|
| `pyproject.toml` | modify | tambah deps `httpx`, `google-api-python-client`, `google-auth` |
| `app/config.py` | modify | field SMTP / Google / WAHA (default kosong) |
| `.env.example` | modify | kunci env baru |
| `app/integrations/email.py` | modify | `SmtpEmail(EmailAdapter)` |
| `app/integrations/calendar.py` | modify | `iter_business_slots`, `CalendarAdapter.create_event` no-op |
| `app/integrations/google_calendar.py` | create | `GoogleCalendar` + `build_google_calendar` |
| `app/integrations/whatsapp.py` | create | `WahaClient.send_text` |
| `app/models/meeting.py` | modify | kolom `google_event_id` |
| `app/repositories/meeting_repo.py` | modify | `set_google_event_id` |
| `alembic/versions/<new>.py` | create | tambah kolom `google_event_id` |
| `app/agent/tools.py` | modify | `create_meeting` buat event + simpan event_id |
| `app/api/chat.py` | modify | providers `get_email`/`get_calendar` (branch) + `get_waha_client` |
| `app/api/whatsapp.py` | create | route `POST /webhook/whatsapp` |
| `app/main.py` | modify | daftarkan router whatsapp |
| `docker-compose.yml` | modify | service `waha` + env app |
| `docs/menjalankan-dengan-docker.md` | modify | langkah WAHA |
| `tests/fakes.py` | modify | `FakeCalendar.create_event` + `event_id` |
| `tests/test_email_smtp.py` | create | unit SmtpEmail |
| `tests/test_google_calendar.py` | create | unit GoogleCalendar |
| `tests/test_whatsapp.py` | create | unit WahaClient + webhook route |
| `tests/test_meeting_repo.py` / `tests/test_tools.py` | modify | event_id |

---

## Task 1: Dependencies + config + .env.example

**Files:**
- Modify: `pyproject.toml`, `app/config.py`, `.env.example`

- [ ] **Step 1: Add runtime dependencies**

Run: `uv add httpx google-api-python-client google-auth`
Expected: `pyproject.toml` `[project.dependencies]` gains the three packages; `uv.lock` updates; no error.

- [ ] **Step 2: Add config fields**

Replace the body of `Settings` in `app/config.py` with (keep existing fields, append the new groups):

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost:5432/efisien_cs"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "gemini-embedding-001"

    # Gmail SMTP (Slice A)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Google Calendar (Slice B)
    google_calendar_id: str = ""
    google_service_account_file: str = ""

    # WhatsApp via WAHA (Slice C)
    waha_base_url: str = ""
    waha_session: str = "default"
    waha_api_key: str = ""
```

- [ ] **Step 3: Update .env.example**

Replace `.env.example` with:

```
DATABASE_URL=postgresql+psycopg://localhost:5432/efisien_cs
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.0-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001

# Gmail SMTP (kirim undangan). Butuh 2FA + App Password.
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=

# Google Calendar (service account JSON + calendar yang di-share ke service account)
GOOGLE_CALENDAR_ID=
GOOGLE_SERVICE_ACCOUNT_FILE=

# WhatsApp via WAHA
WAHA_BASE_URL=
WAHA_SESSION=default
WAHA_API_KEY=
```

- [ ] **Step 4: Verify imports & settings load**

Run: `uv run python -c "import httpx, googleapiclient, google.oauth2.service_account; from app.config import settings; print(settings.smtp_host, settings.waha_session)"`
Expected: `smtp.gmail.com default`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock app/config.py .env.example
git commit -m "chore: deps + config for smtp/google-calendar/waha integrations"
```

---

## Task 2: Gmail SMTP EmailAdapter

**Files:**
- Modify: `app/integrations/email.py`, `app/api/chat.py`
- Test: `tests/test_email_smtp.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_email_smtp.py`:

```python
from app.integrations.email import SmtpEmail


class _FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.sent = msg

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_smtp_email_sends():
    _FakeSMTP.instances = []
    mailer = SmtpEmail(
        host="smtp.gmail.com", port=587, user="me@gmail.com",
        password="app-pass", sender="me@gmail.com", smtp_factory=_FakeSMTP,
    )
    mailer.send("client@example.com", "Undangan", "Jadwal: besok 09:00")
    smtp = _FakeSMTP.instances[-1]
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 587)
    assert smtp.started_tls is True
    assert smtp.logged_in == ("me@gmail.com", "app-pass")
    assert smtp.sent["To"] == "client@example.com"
    assert smtp.sent["Subject"] == "Undangan"
    assert smtp.sent["From"] == "me@gmail.com"
    assert "Jadwal: besok 09:00" in smtp.sent.get_content()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_email_smtp.py -v`
Expected: FAIL — `ImportError: cannot import name 'SmtpEmail'`.

- [ ] **Step 3: Implement SmtpEmail**

Append to `app/integrations/email.py`:

```python
import smtplib
from email.message import EmailMessage


class SmtpEmail(EmailAdapter):
    """Sends real email via SMTP (e.g. Gmail with an App Password)."""

    def __init__(self, *, host, port, user, password, sender, smtp_factory=smtplib.SMTP):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._sender = sender or user
        self._smtp_factory = smtp_factory

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with self._smtp_factory(self._host, self._port) as smtp:
            smtp.starttls()
            smtp.login(self._user, self._password)
            smtp.send_message(msg)
```

- [ ] **Step 4: Wire get_email() to branch on config**

In `app/api/chat.py`, add the settings import near the top:

```python
from app.config import settings
```

Change the email import to include `SmtpEmail`:

```python
from app.integrations.email import ConsoleEmail, SmtpEmail
```

Replace `get_email`:

```python
def get_email():
    if settings.smtp_user and settings.smtp_password:
        return SmtpEmail(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            sender=settings.smtp_from or settings.smtp_user,
        )
    return ConsoleEmail()
```

(`app/api/chat.py` currently imports `from app.integrations.email import ConsoleEmail`; widen it as above.)

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_email_smtp.py -v`
Expected: PASS (1 test).

- [ ] **Step 6: Commit**

```bash
git add app/integrations/email.py app/api/chat.py tests/test_email_smtp.py
git commit -m "feat: SmtpEmail adapter (Gmail SMTP) + config-based wiring"
```

---

## Task 3: Calendar refactor + create_event hook

**Files:**
- Modify: `app/integrations/calendar.py`
- Test: `tests/test_calendar.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_calendar.py`:

```python
def test_create_event_default_is_noop():
    from datetime import datetime

    from app.integrations.calendar import WIB, LocalCalendar

    out = LocalCalendar().create_event(
        datetime(2099, 1, 5, 9, 0, tzinfo=WIB), summary="x", description="y"
    )
    assert out is None


def test_iter_business_slots_skips_weekends_and_past():
    from datetime import datetime

    from app.integrations.calendar import WIB, fmt_slot, iter_business_slots

    now = datetime(2099, 1, 4, 0, 0, tzinfo=WIB)
    slots = iter_business_slots(now)
    assert slots, "should produce business-hour slots"
    # all slots strictly after `now` and within 09:00..16:00
    assert all(s > now for s in slots)
    assert all(9 <= s.hour <= 16 for s in slots)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_calendar.py -k "create_event_default or iter_business_slots" -v`
Expected: FAIL — `ImportError`/`AttributeError` (no `iter_business_slots`, no `create_event`).

- [ ] **Step 3: Refactor calendar.py**

In `app/integrations/calendar.py`, add the module-level helper after `parse_slot`:

```python
def iter_business_slots(now: datetime) -> list[datetime]:
    """All future business-hour slots within the horizon (no booking awareness)."""
    now_w = to_wib(now)
    start = now_w.date()
    result: list[datetime] = []
    for offset in range(HORIZON_DAYS):
        day = start + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for hour in range(WORK_START, WORK_END):
            slot = datetime(day.year, day.month, day.day, hour, 0, tzinfo=WIB)
            if slot <= now_w:
                continue
            result.append(slot)
    return result
```

Add a default `create_event` to the ABC:

```python
class CalendarAdapter(ABC):
    @abstractmethod
    def available_slots(self, booked: set[datetime], *, now: datetime) -> list[datetime]:
        ...

    def create_event(self, start: datetime, *, summary: str, description: str) -> str | None:
        """Optional: create a real calendar event; default no-op returns None."""
        return None
```

Replace `LocalCalendar.available_slots` body to reuse the helper:

```python
class LocalCalendar(CalendarAdapter):
    """Business-hour slots for the next HORIZON_DAYS, minus booked meetings."""

    def available_slots(self, booked: set[datetime], *, now: datetime) -> list[datetime]:
        booked_keys = {fmt_slot(b) for b in booked}
        return [s for s in iter_business_slots(now) if fmt_slot(s) not in booked_keys]
```

- [ ] **Step 4: Run tests (new + existing calendar suite)**

Run: `uv run pytest tests/test_calendar.py -v`
Expected: PASS — both new tests and all pre-existing LocalCalendar tests stay green.

- [ ] **Step 5: Commit**

```bash
git add app/integrations/calendar.py tests/test_calendar.py
git commit -m "refactor: iter_business_slots helper + CalendarAdapter.create_event hook"
```

---

## Task 4: meetings.google_event_id (model + migration + repo)

**Files:**
- Modify: `app/models/meeting.py`, `app/repositories/meeting_repo.py`
- Create: `alembic/versions/<generated>.py`
- Test: `tests/test_meeting_repo.py`

**Prasyarat untuk Step 5 (apply):** PostgreSQL (Postgres.app) menyala.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_meeting_repo.py`:

```python
def test_set_google_event_id(session):
    from datetime import datetime

    from app.integrations.calendar import WIB
    from app.models.user import User
    from app.repositories.lead_repo import LeadRepository
    from app.repositories.meeting_repo import MeetingRepository

    u = User(name="K", phone="0890")
    session.add(u)
    session.flush()
    lead = LeadRepository(session).upsert(u.id, project_type="POS")
    repo = MeetingRepository(session)
    m = repo.create(lead.id, datetime(2099, 1, 5, 9, 0, tzinfo=WIB), "https://meet/x")
    repo.set_google_event_id(m, "evt-123")
    assert m.google_event_id == "evt-123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_meeting_repo.py::test_set_google_event_id -v`
Expected: FAIL — `AttributeError` (`google_event_id` / `set_google_event_id` missing).

- [ ] **Step 3: Add the column**

In `app/models/meeting.py`, add after the `meeting_link` line:

```python
    google_event_id: Mapped[str | None] = mapped_column(String(255))
```

- [ ] **Step 4: Add the repository method**

In `app/repositories/meeting_repo.py`, add to `MeetingRepository`:

```python
    def set_google_event_id(self, meeting: Meeting, event_id: str) -> Meeting:
        meeting.google_event_id = event_id
        self.session.flush()
        return meeting
```

- [ ] **Step 5: Create and apply the migration (needs Postgres)**

Run: `uv run alembic revision -m "add google_event_id to meetings"`
Then edit the new file's `upgrade`/`downgrade`:

```python
def upgrade() -> None:
    op.add_column("meetings", sa.Column("google_event_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("meetings", "google_event_id")
```

Apply: `uv run alembic upgrade head`
Expected: `Running upgrade cb654acf820e -> <hash>, add google_event_id to meetings`.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_meeting_repo.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/models/meeting.py app/repositories/meeting_repo.py alembic/versions/ tests/test_meeting_repo.py
git commit -m "feat: meetings.google_event_id column + repo setter + migration"
```

---

## Task 5: create_meeting creates calendar event + stores event_id

**Files:**
- Modify: `tests/fakes.py`, `app/agent/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Extend FakeCalendar**

Replace `tests/fakes.py` `FakeCalendar` with:

```python
class FakeCalendar:
    """Returns a fixed slot list (minus booked) regardless of `now` — deterministic."""

    def __init__(self, slots, event_id=None):
        self._slots = list(slots)
        self._event_id = event_id
        self.created = []

    def available_slots(self, booked, *, now):
        return [s for s in self._slots if s not in booked]

    def create_event(self, start, *, summary, description):
        self.created.append((start, summary, description))
        return self._event_id
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_tools.py`:

```python
def test_dispatch_create_meeting_stores_google_event_id(session):
    user = _seed_user(session, phone="0826")
    LeadRepository(session).upsert(user.id, project_type="POS")
    cal = FakeCalendar([_SLOT], event_id="evt-123")
    out = json.loads(
        dispatch(
            ToolCall(name="create_meeting", args={"slot": "2099-01-05 09:00"}),
            session=session,
            user=user,
            calendar=cal,
        )
    )
    assert out["google_event_id"] == "evt-123"
    assert cal.created  # create_event was invoked with the booked slot
```

(`_SLOT`, `FakeCalendar`, `LeadRepository`, and `json` are already imported in `tests/test_tools.py`.)

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py::test_dispatch_create_meeting_stores_google_event_id -v`
Expected: FAIL — current response has no `google_event_id` key → KeyError.

- [ ] **Step 4: Update create_meeting in tools.py**

In `app/agent/tools.py`, replace the `create_meeting` write/return block (the part that builds `meeting` and returns its JSON) with:

```python
            link = _meeting_link()
            meeting = MeetingRepository(session).create(lead.id, parse_slot(chosen), link)
            try:
                event_id = calendar.create_event(
                    parse_slot(chosen),
                    summary="Konsultasi - PT Efisien Integrasi Indonesia",
                    description=f"Link: {link}",
                )
                if event_id:
                    MeetingRepository(session).set_google_event_id(meeting, event_id)
            except Exception:
                pass  # calendar is best-effort; the booking is already saved
            return json.dumps(
                {
                    "meeting_id": meeting.id,
                    "meeting_time": chosen,
                    "meeting_link": meeting.meeting_link,
                    "status": meeting.status,
                    "google_event_id": meeting.google_event_id,
                },
                ensure_ascii=False,
            )
```

- [ ] **Step 5: Run tests (new + existing tools/meeting suites)**

Run: `uv run pytest tests/test_tools.py tests/test_orchestrator.py tests/test_chat_api.py -q`
Expected: all pass — existing booking tests still green (FakeCalendar now exposes a no-op-ish `create_event` returning None unless `event_id` set).

- [ ] **Step 6: Commit**

```bash
git add tests/fakes.py app/agent/tools.py tests/test_tools.py
git commit -m "feat: create_meeting creates calendar event + stores google_event_id"
```

---

## Task 6: GoogleCalendar adapter + factory + wiring

**Files:**
- Create: `app/integrations/google_calendar.py`
- Modify: `app/api/chat.py`
- Test: `tests/test_google_calendar.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_google_calendar.py`:

```python
from datetime import datetime, timedelta

from app.integrations.calendar import WIB, fmt_slot, iter_business_slots
from app.integrations.google_calendar import GoogleCalendar

CAL = "cal@example.com"


class _FakeFreebusy:
    def __init__(self, busy):
        self._busy = busy

    def query(self, body=None):
        self._body = body
        return self

    def execute(self):
        return {"calendars": {CAL: {"busy": self._busy}}}


class _FakeEvents:
    def __init__(self, store):
        self._store = store

    def insert(self, calendarId=None, body=None):
        self._store["calendarId"] = calendarId
        self._store["body"] = body
        return self

    def execute(self):
        return {"id": "evt-xyz"}


class _FakeService:
    def __init__(self, busy):
        self._fb = _FakeFreebusy(busy)
        self.store = {}

    def freebusy(self):
        return self._fb

    def events(self):
        return _FakeEvents(self.store)


def test_available_slots_excludes_busy():
    now = datetime(2099, 1, 4, 0, 0, tzinfo=WIB)
    target = iter_business_slots(now)[0]
    busy = [{"start": target.isoformat(), "end": (target + timedelta(hours=1)).isoformat()}]
    cal = GoogleCalendar(_FakeService(busy), CAL)
    keys = {fmt_slot(s) for s in cal.available_slots(set(), now=now)}
    assert fmt_slot(target) not in keys
    assert fmt_slot(iter_business_slots(now)[1]) in keys


def test_create_event_inserts_and_returns_id():
    cal = GoogleCalendar(_FakeService([]), CAL)
    eid = cal.create_event(
        datetime(2099, 1, 5, 9, 0, tzinfo=WIB), summary="Konsultasi", description="Link: x"
    )
    assert eid == "evt-xyz"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_google_calendar.py -v`
Expected: FAIL — `ModuleNotFoundError: app.integrations.google_calendar`.

- [ ] **Step 3: Implement GoogleCalendar + factory**

Create `app/integrations/google_calendar.py`:

```python
from datetime import datetime, timedelta

from app.integrations.calendar import (
    CalendarAdapter,
    fmt_slot,
    iter_business_slots,
    to_wib,
)


class GoogleCalendar(CalendarAdapter):
    """Reads freebusy and creates events on a Google Calendar via an injected service."""

    def __init__(self, service, calendar_id: str) -> None:
        self._service = service
        self._calendar_id = calendar_id

    def available_slots(self, booked, *, now):
        slots = iter_business_slots(now)
        if not slots:
            return []
        resp = (
            self._service.freebusy()
            .query(
                body={
                    "timeMin": to_wib(now).isoformat(),
                    "timeMax": (slots[-1] + timedelta(hours=1)).isoformat(),
                    "items": [{"id": self._calendar_id}],
                }
            )
            .execute()
        )
        busy_raw = resp.get("calendars", {}).get(self._calendar_id, {}).get("busy", [])
        busy = [
            (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
            for b in busy_raw
        ]
        booked_keys = {fmt_slot(b) for b in booked}
        result = []
        for s in slots:
            if fmt_slot(s) in booked_keys:
                continue
            if any(bs <= s < be for bs, be in busy):
                continue
            result.append(s)
        return result

    def create_event(self, start, *, summary, description):
        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": to_wib(start).isoformat(), "timeZone": "Asia/Jakarta"},
            "end": {
                "dateTime": to_wib(start + timedelta(hours=1)).isoformat(),
                "timeZone": "Asia/Jakarta",
            },
        }
        event = self._service.events().insert(calendarId=self._calendar_id, body=body).execute()
        return event.get("id")


def build_google_calendar(settings) -> GoogleCalendar:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        settings.google_service_account_file,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return GoogleCalendar(service, settings.google_calendar_id)
```

- [ ] **Step 4: Wire get_calendar() to branch on config**

In `app/api/chat.py`, add the import:

```python
from app.integrations.google_calendar import build_google_calendar
```

Replace `get_calendar`:

```python
def get_calendar():
    if settings.google_calendar_id and settings.google_service_account_file:
        return build_google_calendar(settings)
    return LocalCalendar()
```

(`LocalCalendar` is already imported in `app/api/chat.py`.)

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_google_calendar.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add app/integrations/google_calendar.py app/api/chat.py tests/test_google_calendar.py
git commit -m "feat: GoogleCalendar adapter (freebusy + create event) + wiring"
```

---

## Task 7: WahaClient

**Files:**
- Create: `app/integrations/whatsapp.py`
- Test: `tests/test_whatsapp.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_whatsapp.py`:

```python
from app.integrations.whatsapp import WahaClient


class _FakeResp:
    def raise_for_status(self):
        return None


class _FakeHttpx:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResp()


def test_waha_send_text():
    fake = _FakeHttpx()
    waha = WahaClient(base_url="http://waha:3000", session="default", api_key="secret", client=fake)
    waha.send_text("628111@c.us", "halo")
    call = fake.calls[-1]
    assert call["url"] == "http://waha:3000/api/sendText"
    assert call["json"] == {"session": "default", "chatId": "628111@c.us", "text": "halo"}
    assert call["headers"]["X-Api-Key"] == "secret"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_whatsapp.py::test_waha_send_text -v`
Expected: FAIL — `ModuleNotFoundError: app.integrations.whatsapp`.

- [ ] **Step 3: Implement WahaClient**

Create `app/integrations/whatsapp.py`:

```python
import httpx


class WahaClient:
    """Minimal client for the WAHA WhatsApp HTTP API."""

    def __init__(self, *, base_url: str, session: str, api_key: str, client=None) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = session
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=30)

    def send_text(self, chat_id: str, text: str) -> None:
        resp = self._client.post(
            f"{self._base_url}/api/sendText",
            json={"session": self._session, "chatId": chat_id, "text": text},
            headers={"X-Api-Key": self._api_key},
        )
        resp.raise_for_status()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_whatsapp.py::test_waha_send_text -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/integrations/whatsapp.py tests/test_whatsapp.py
git commit -m "feat: WahaClient (WhatsApp HTTP API send_text)"
```

---

## Task 8: WhatsApp webhook route

**Files:**
- Modify: `app/api/chat.py` (add `get_waha_client`), `app/main.py`
- Create: `app/api/whatsapp.py`
- Test: `tests/test_whatsapp.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_whatsapp.py`:

```python
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chat import get_calendar, get_email, get_llm, get_retriever, get_waha_client
from app.db import get_session
from app.llm.fake import FakeLLM
from app.main import app
from app.models.base import Base
from app.models.user import User  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.lead import Lead  # noqa: F401
from app.models.meeting import Meeting  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.ticket import Ticket  # noqa: F401
from app.models.client_fact import ClientFact  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from tests.fakes import FakeCalendar, FakeEmail


class _EmptyRetriever:
    def search(self, query, k=4):
        return []


class _CapturingWaha:
    def __init__(self):
        self.sent = []

    def send_text(self, chat_id, text):
        self.sent.append((chat_id, text))


def _webhook_client(llm, waha):
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with TestSession() as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_retriever] = lambda: _EmptyRetriever()
    app.dependency_overrides[get_calendar] = lambda: FakeCalendar([])
    app.dependency_overrides[get_email] = lambda: FakeEmail()
    app.dependency_overrides[get_waha_client] = lambda: waha
    return TestClient(app)


def test_webhook_processes_message_and_replies():
    waha = _CapturingWaha()
    client = _webhook_client(FakeLLM(reply="Halo!"), waha)
    payload = {"event": "message", "payload": {"from": "628111@c.us", "body": "halo", "fromMe": False}}
    r = client.post("/webhook/whatsapp", json=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert waha.sent == [("628111@c.us", "Halo!")]
    app.dependency_overrides.clear()


def test_webhook_ignores_fromme_and_groups():
    waha = _CapturingWaha()
    client = _webhook_client(FakeLLM(reply="x"), waha)
    fromme = {"event": "message", "payload": {"from": "628@c.us", "body": "hi", "fromMe": True}}
    group = {"event": "message", "payload": {"from": "123@g.us", "body": "hi", "fromMe": False}}
    assert client.post("/webhook/whatsapp", json=fromme).json()["status"] == "ignored"
    assert client.post("/webhook/whatsapp", json=group).json()["status"] == "ignored"
    assert waha.sent == []
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_whatsapp.py -k webhook -v`
Expected: FAIL — `ImportError` (`get_waha_client` missing) / route 404.

- [ ] **Step 3: Add get_waha_client to chat.py**

In `app/api/chat.py`, add the import and provider:

```python
from app.integrations.whatsapp import WahaClient


def get_waha_client():
    return WahaClient(
        base_url=settings.waha_base_url,
        session=settings.waha_session,
        api_key=settings.waha_api_key,
    )
```

- [ ] **Step 4: Create the webhook route**

Create `app/api/whatsapp.py`:

```python
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.agent.orchestrator import handle_chat
from app.api.chat import get_calendar, get_email, get_llm, get_retriever, get_waha_client
from app.db import get_session

router = APIRouter()


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    session: Session = Depends(get_session),
    llm=Depends(get_llm),
    retriever=Depends(get_retriever),
    calendar=Depends(get_calendar),
    mailer=Depends(get_email),
    waha=Depends(get_waha_client),
) -> dict[str, str]:
    data = await request.json()
    if data.get("event") != "message":
        return {"status": "ignored"}
    payload = data.get("payload") or {}
    chat_id = payload.get("from") or ""
    body = payload.get("body") or ""
    if payload.get("fromMe") or chat_id.endswith("@g.us") or not body.strip():
        return {"status": "ignored"}
    phone = chat_id.split("@")[0]
    reply, _user = handle_chat(
        session, llm, retriever, message=body, phone=phone, calendar=calendar, mailer=mailer
    )
    waha.send_text(chat_id, reply)
    return {"status": "ok"}
```

- [ ] **Step 5: Register the router**

In `app/main.py`, add the import and include it **before** the static mount:

```python
from app.api.whatsapp import router as whatsapp_router
```

```python
app.include_router(whatsapp_router)
```

(Place `app.include_router(whatsapp_router)` right after the existing `app.include_router(router)` line and before `app.mount("/", ...)`.)

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_whatsapp.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add app/api/chat.py app/api/whatsapp.py app/main.py tests/test_whatsapp.py
git commit -m "feat: /webhook/whatsapp channel (WAHA inbound -> agent -> reply)"
```

---

## Task 9: Docker Compose (WAHA service) + docs

**Files:**
- Modify: `docker-compose.yml`, `docs/menjalankan-dengan-docker.md`

- [ ] **Step 1: Add the WAHA service and app env**

In `docker-compose.yml`, add `WAHA_BASE_URL` to the `app` service `environment` block (keep `DATABASE_URL`):

```yaml
    environment:
      DATABASE_URL: postgresql+psycopg://efisien:efisien@db:5432/efisien_cs
      WAHA_BASE_URL: http://waha:3000
```

Add a `waha` service (sibling of `db`/`app`):

```yaml
  waha:
    image: devlikeapro/waha
    ports:
      - "3000:3000"
    environment:
      WHATSAPP_HOOK_URL: http://app:8000/webhook/whatsapp
      WHATSAPP_HOOK_EVENTS: message
      WAHA_API_KEY: ${WAHA_API_KEY:-}
    volumes:
      - waha_sessions:/app/.sessions
```

Add the volume under `volumes:`:

```yaml
  waha_sessions:
```

(`SMTP_*`, `GOOGLE_*`, `WAHA_SESSION`, `WAHA_API_KEY` for the app come from `env_file: .env`; `WAHA_BASE_URL` is set explicitly to reach the `waha` service.)

- [ ] **Step 2: Validate compose**

Run: `docker compose config >/dev/null && echo "compose OK"` (skip with a note if Docker is unavailable).
Expected: `compose OK`.

- [ ] **Step 3: Document usage**

Append to `docs/menjalankan-dengan-docker.md`:

```markdown

## Integrasi nyata (opsional)

Isi di `.env` untuk mengaktifkan integrasi (kosong = fallback aman):

- **Gmail SMTP:** `SMTP_USER`, `SMTP_PASSWORD` (App Password Gmail; 2FA wajib aktif), `SMTP_FROM` opsional.
- **Google Calendar:** `GOOGLE_SERVICE_ACCOUNT_FILE` (path file JSON service account, mount ke container), `GOOGLE_CALENDAR_ID` (calendar yang di-share ke email service account).
- **WhatsApp (WAHA):** `WAHA_API_KEY` (sama dengan yang dipakai service `waha`). `WAHA_BASE_URL`/`WAHA_SESSION` sudah diset oleh Compose.

### Mengaktifkan WhatsApp
1. `docker compose up --build` (menyalakan `app`, `db`, dan `waha`).
2. Buka dashboard WAHA di **http://localhost:3000**, mulai session `default`, lalu **scan QR** dengan WhatsApp di HP.
3. WAHA otomatis mengirim pesan masuk ke `http://app:8000/webhook/whatsapp`; agen membalas via WhatsApp.

> Catatan: nama variabel env internal WAHA mengikuti dokumentasi image `devlikeapro/waha`; sesuaikan bila versi image berbeda.
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml docs/menjalankan-dengan-docker.md
git commit -m "feat: WAHA service in compose + integration docs"
```

---

## Task 10: Full suite + final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `uv run pytest -q`
Expected: all pass (84 prior + 9 new ≈ 93 total). No failures.

- [ ] **Step 2: App imports cleanly (routes registered)**

Run: `uv run python -c "from app.main import app; print(sorted({r.path for r in app.routes if getattr(r, 'path', '').startswith('/')}) [:5]); print('/webhook/whatsapp' in {getattr(r,'path','') for r in app.routes})"`
Expected: prints route paths and `True` (webhook registered).

- [ ] **Step 3: Migration at head (needs Postgres)**

Run: `uv run alembic current`
Expected: shows the `google_event_id` revision as head.

- [ ] **Step 4: Compose valid (if Docker available)**

Run: `docker compose config >/dev/null && echo "compose OK"`
Expected: `compose OK`.

---

## Self-Review

**Spec coverage:**
- §1 Slice A SmtpEmail + wiring → Task 2 ✓
- §2 Slice B create_event hook + iter_business_slots → Task 3; GoogleCalendar + factory + wiring → Task 6; meetings.google_event_id (model/migration/repo) → Task 4; create_meeting stores event_id → Task 5 ✓
- §3 Slice C WahaClient → Task 7; webhook route + get_waha_client + register → Task 8 ✓
- §4 deps + config + .env.example → Task 1; Compose waha + docs → Task 9 ✓
- §5 Error handling → SMTP via dispatch try/except (existing), calendar best-effort (Task 5), webhook ignore-safe (Task 8), fallbacks (Tasks 2/6) ✓
- §6 Testing (smtp/google/waha/webhook/event_id) → Tasks 2,3,4,5,6,7,8 ✓
- §7 DOD → Task 10 ✓

**Type consistency:** `SmtpEmail(host,port,user,password,sender,smtp_factory)`; `CalendarAdapter.create_event(start,*,summary,description)->str|None`; `iter_business_slots(now)`; `GoogleCalendar(service,calendar_id)`; `build_google_calendar(settings)`; `MeetingRepository.set_google_event_id(meeting,event_id)`; `WahaClient(base_url=,session=,api_key=,client=)` + `send_text(chat_id,text)`; `get_email/get_calendar/get_waha_client` providers. Config field names match `.env.example` keys (uppercased). Consistent across tasks.

**Placeholder scan:** none — every step has concrete code/commands.
