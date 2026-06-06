# Sprint 6 — Memory + Human Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tambahkan memori jangka panjang (`client_fact` + tool `remember_fact`, dimuat ke system prompt tiap giliran) dan human handoff (`notification` + tool `notify_sales`/`notify_manager`).

**Architecture:** Lean — tanpa service layer. Repository dipanggil langsung dari `dispatch`. Identitas user di-inject dari context. Dua model baru (`client_facts`, `notifications`) + repository. Satu perubahan orchestrator: muat fakta user → tempel ke string `system` sebelum loop. Satu migration Alembic. TDD penuh dengan SQLite in-memory + FakeLLM.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL (prod) / SQLite in-memory (test), pytest, `uv`.

---

## File Structure

| File | Tanggung jawab |
|---|---|
| `app/models/client_fact.py` (create) | ORM model `client_facts` (unique user_id+key) |
| `app/models/notification.py` (create) | ORM model `notifications` |
| `app/repositories/client_fact_repo.py` (create) | upsert + list fakta |
| `app/repositories/notification_repo.py` (create) | create notifikasi |
| `app/agent/tools.py` (modify) | 3 ToolSpec + 3 cabang dispatch (`remember_fact`, `notify_sales`, `notify_manager`) + helper `_notify` |
| `app/agent/orchestrator.py` (modify) | muat fakta → tempel ke `system`; helper `_memory_block` |
| `app/agent/prompts.py` (modify) | paragraf memori + handoff |
| `alembic/versions/<new>.py` (create) | migration client_facts + notifications |
| `alembic/env.py` (modify) | register model baru |
| `tests/conftest.py` (modify) | import model baru |
| `tests/test_client_fact_repo.py` (create) | unit ClientFactRepository |
| `tests/test_notification_repo.py` (create) | unit NotificationRepository |
| `tests/test_tools.py` (modify) | test 3 tool baru |
| `tests/test_orchestrator.py` (modify) | memori di system prompt + loop remember/handoff |
| `tests/test_chat_api.py` (modify) | e2e wiring handoff |

---

## Task 1: ClientFact model + ClientFactRepository

**Files:**
- Create: `app/models/client_fact.py`
- Create: `app/repositories/client_fact_repo.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_client_fact_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_client_fact_repo.py`:

```python
from app.models.user import User
from app.repositories.client_fact_repo import ClientFactRepository


def _user(session):
    u = User(name="Klien", phone="0870")
    session.add(u)
    session.flush()
    return u


def test_upsert_creates_then_updates(session):
    u = _user(session)
    repo = ClientFactRepository(session)
    repo.upsert(u.id, "nama", "Budi")
    repo.upsert(u.id, "perusahaan", "Toko Maju")
    repo.upsert(u.id, "nama", "Andi")  # same key -> update, not insert
    facts = repo.list_for_user(u.id)
    assert len(facts) == 2
    by_key = {f.key: f.value for f in facts}
    assert by_key["nama"] == "Andi"
    assert by_key["perusahaan"] == "Toko Maju"


def test_list_for_user_empty(session):
    u = _user(session)
    assert ClientFactRepository(session).list_for_user(u.id) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_client_fact_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.repositories.client_fact_repo'`

- [ ] **Step 3: Create the model**

Create `app/models/client_fact.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClientFact(Base):
    __tablename__ = "client_facts"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_client_facts_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    key: Mapped[str] = mapped_column(String(60))
    value: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 4: Register the model in conftest**

In `tests/conftest.py`, add after the `Ticket` import:

```python
from app.models.client_fact import ClientFact  # noqa: F401  (register table)
```

- [ ] **Step 5: Create the repository**

Create `app/repositories/client_fact_repo.py`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client_fact import ClientFact


class ClientFactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, user_id: int, key: str, value: str) -> ClientFact:
        fact = self.session.scalar(
            select(ClientFact).where(
                ClientFact.user_id == user_id, ClientFact.key == key
            )
        )
        if fact is None:
            fact = ClientFact(user_id=user_id, key=key, value=value)
            self.session.add(fact)
        else:
            fact.value = value
        self.session.flush()
        return fact

    def list_for_user(self, user_id: int) -> list[ClientFact]:
        return list(
            self.session.scalars(
                select(ClientFact).where(ClientFact.user_id == user_id).order_by(ClientFact.id)
            )
        )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_client_fact_repo.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add app/models/client_fact.py app/repositories/client_fact_repo.py tests/conftest.py tests/test_client_fact_repo.py
git commit -m "feat: ClientFact model + ClientFactRepository (upsert, list_for_user)"
```

---

## Task 2: Notification model + NotificationRepository

**Files:**
- Create: `app/models/notification.py`
- Create: `app/repositories/notification_repo.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_notification_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_notification_repo.py`:

```python
from app.repositories.notification_repo import NotificationRepository


def test_create_notification_is_sent(session):
    n = NotificationRepository(session).create(
        "manager", reason="komplain pembayaran", payload={"name": "Budi", "phone": "0870"}
    )
    assert n.id is not None
    assert n.target_role == "manager"
    assert n.status == "sent"
    assert n.reason == "komplain pembayaran"
    assert n.payload == {"name": "Budi", "phone": "0870"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_notification_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.repositories.notification_repo'`

- [ ] **Step 3: Create the model**

Create `app/models/notification.py`:

```python
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_role: Mapped[str] = mapped_column(String(16))  # sales/manager/developer
    reason: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="sent", server_default="sent")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 4: Register the model in conftest**

In `tests/conftest.py`, add after the `ClientFact` import:

```python
from app.models.notification import Notification  # noqa: F401  (register table)
```

- [ ] **Step 5: Create the repository**

Create `app/repositories/notification_repo.py`:

```python
from sqlalchemy.orm import Session

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, target_role: str, *, reason: str, payload: dict | None = None) -> Notification:
        notif = Notification(
            target_role=target_role, reason=reason, payload=payload, status="sent"
        )
        self.session.add(notif)
        self.session.flush()
        return notif
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_notification_repo.py -v`
Expected: PASS (1 test)

- [ ] **Step 7: Commit**

```bash
git add app/models/notification.py app/repositories/notification_repo.py tests/conftest.py tests/test_notification_repo.py
git commit -m "feat: Notification model + NotificationRepository (create, status sent)"
```

---

## Task 3: Alembic migration (client_facts + notifications)

**Files:**
- Modify: `alembic/env.py`
- Create: `alembic/versions/<generated>.py`

**Prasyarat:** PostgreSQL (Postgres.app) menyala. DB: `efisien_cs`.

- [ ] **Step 1: Register models in alembic env**

In `alembic/env.py`, add after the `Ticket` import:

```python
from app.models.client_fact import ClientFact  # noqa: F401  (register table)
from app.models.notification import Notification  # noqa: F401  (register table)
```

- [ ] **Step 2: Create an empty revision**

Run: `uv run alembic revision -m "create client_facts and notifications"`
Expected: prints the new file path. Its `down_revision` is auto-set to `'1f6b4f955bf9'`.

- [ ] **Step 3: Fill in upgrade/downgrade**

Open the newly created file and replace the `upgrade()` and `downgrade()` bodies with:

```python
def upgrade() -> None:
    op.create_table(
        "client_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_client_facts_user_key"),
    )
    op.create_index(op.f("ix_client_facts_user_id"), "client_facts", ["user_id"], unique=False)
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_role", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="sent", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_index(op.f("ix_client_facts_user_id"), table_name="client_facts")
    op.drop_table("client_facts")
```

- [ ] **Step 4: Apply the migration**

Run: `uv run alembic upgrade head`
Expected: `Running upgrade 1f6b4f955bf9 -> <hash>, create client_facts and notifications`. No errors.

- [ ] **Step 5: Verify the schema**

Run: `psql efisien_cs -c "\d client_facts" -c "\d notifications"`
Expected: both tables exist; `client_facts` has unique constraint `uq_client_facts_user_key`; `notifications.status` default `'sent'`.

- [ ] **Step 6: Commit**

```bash
git add alembic/env.py alembic/versions/
git commit -m "feat: add client_facts + notifications tables (migration)"
```

---

## Task 4: remember_fact tool

**Files:**
- Modify: `app/agent/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tools.py`:

```python
from app.repositories.client_fact_repo import ClientFactRepository


def test_dispatch_remember_fact_upserts(session):
    user = _seed_user(session, phone="0840")
    dispatch(
        ToolCall(name="remember_fact", args={"key": "nama", "value": "Budi"}),
        session=session,
        user=user,
    )
    out = json.loads(
        dispatch(
            ToolCall(name="remember_fact", args={"key": "nama", "value": "Andi"}),
            session=session,
            user=user,
        )
    )
    assert out["key"] == "nama"
    assert out["value"] == "Andi"
    facts = ClientFactRepository(session).list_for_user(user.id)
    assert len(facts) == 1
    assert facts[0].value == "Andi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py::test_dispatch_remember_fact_upserts -v`
Expected: FAIL — unknown tool error → KeyError on `out["key"]`.

- [ ] **Step 3: Add the repo imports**

In `app/agent/tools.py`, add after the existing repo imports:

```python
from app.repositories.client_fact_repo import ClientFactRepository
from app.repositories.notification_repo import NotificationRepository
```

- [ ] **Step 4: Add the ToolSpec**

Add this `ToolSpec` to `TOOL_SPECS` (after the `assign_developer` spec):

```python
    ToolSpec(
        name="remember_fact",
        description=(
            "Simpan fakta durable tentang user (mis. nama, perusahaan, peran, preferensi) "
            "agar diingat di percakapan berikutnya. Panggil saat user menyebutkan info "
            "tentang dirinya yang layak diingat."
        ),
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Label fakta, mis. 'nama', 'perusahaan'"},
                "value": {"type": "string", "description": "Isi fakta"},
            },
            "required": ["key", "value"],
        },
    ),
```

- [ ] **Step 5: Add the dispatch branch**

In `app/agent/tools.py`, add this branch inside `dispatch` (after the `assign_developer` branch, before the final unknown-tool `return`):

```python
        if tool_call.name == "remember_fact":
            key = tool_call.args.get("key", "")
            value = tool_call.args.get("value", "")
            ClientFactRepository(session).upsert(user.id, key, value)
            return json.dumps(
                {"key": key, "value": value, "result": "Fakta disimpan."},
                ensure_ascii=False,
            )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_tools.py::test_dispatch_remember_fact_upserts -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/agent/tools.py tests/test_tools.py
git commit -m "feat: remember_fact tool (upsert client_fact, inject user)"
```

---

## Task 5: notify_sales + notify_manager tools

**Files:**
- Modify: `app/agent/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tools.py`:

```python
from app.models.notification import Notification


def test_dispatch_notify_sales_writes_row(session):
    user = _seed_user(session, phone="0841", email="a@mail.com")
    out = json.loads(
        dispatch(
            ToolCall(name="notify_sales", args={"reason": "minta penawaran khusus"}),
            session=session,
            user=user,
        )
    )
    assert out["target_role"] == "sales"
    assert out["status"] == "sent"
    notif = session.get(Notification, out["notification_id"])
    assert notif.reason == "minta penawaran khusus"
    assert notif.payload["email"] == "a@mail.com"
    assert notif.payload["phone"] == "0841"


def test_dispatch_notify_manager_writes_row(session):
    user = _seed_user(session, phone="0842")
    out = json.loads(
        dispatch(
            ToolCall(name="notify_manager", args={"reason": "komplain"}),
            session=session,
            user=user,
        )
    )
    assert out["target_role"] == "manager"
    notif = session.get(Notification, out["notification_id"])
    assert notif.target_role == "manager"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py -k "notify_sales or notify_manager" -v`
Expected: FAIL — unknown tool error.

- [ ] **Step 3: Add the two ToolSpecs**

Add these `ToolSpec`s to `TOOL_SPECS` (after the `remember_fact` spec):

```python
    ToolSpec(
        name="notify_sales",
        description=(
            "Teruskan ke tim sales saat ada peluang/permintaan komersial yang butuh "
            "manusia (mis. negosiasi harga, penawaran khusus). Isi 'reason' yang jelas."
        ),
        parameters={
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Alasan eskalasi ke sales"}},
            "required": ["reason"],
        },
    ),
    ToolSpec(
        name="notify_manager",
        description=(
            "Eskalasi ke manajer saat user minta bicara dengan manusia, ada komplain "
            "pembayaran/kontrak, atau kegagalan berulang. Isi 'reason' yang jelas."
        ),
        parameters={
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Alasan eskalasi ke manajer"}},
            "required": ["reason"],
        },
    ),
```

- [ ] **Step 4: Add the `_notify` helper**

In `app/agent/tools.py`, add after the `_CATEGORIES`/`_PRIORITIES` constants:

```python
def _notify(session, user, role: str, reason: str) -> str:
    payload = {"name": user.name, "phone": user.phone, "email": user.email}
    notif = NotificationRepository(session).create(role, reason=reason, payload=payload)
    print(f"[NOTIFY:{role}] {reason} | user={user.name or user.phone or user.email}")
    return json.dumps(
        {
            "notification_id": notif.id,
            "target_role": notif.target_role,
            "status": notif.status,
            "result": f"Diteruskan ke tim {role}; akan menindaklanjuti.",
        },
        ensure_ascii=False,
    )
```

- [ ] **Step 5: Add the dispatch branches**

Add these branches inside `dispatch` (after the `remember_fact` branch):

```python
        if tool_call.name == "notify_sales":
            return _notify(session, user, "sales", tool_call.args.get("reason", ""))

        if tool_call.name == "notify_manager":
            return _notify(session, user, "manager", tool_call.args.get("reason", ""))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py -k "notify_sales or notify_manager" -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add app/agent/tools.py tests/test_tools.py
git commit -m "feat: notify_sales/notify_manager tools (write notification + console log)"
```

---

## Task 6: System prompt — memory + handoff

**Files:**
- Modify: `app/agent/prompts.py`

- [ ] **Step 1: Add the guidance paragraphs**

In `app/agent/prompts.py`, insert the following **before** the final `PENTING:` paragraph:

```python
Saat user menyebut fakta durable tentang dirinya (nama, perusahaan, peran, preferensi),
panggil `remember_fact(key, value)` untuk menyimpannya. Manfaatkan fakta yang sudah
diketahui (lihat blok memori di awal instruksi, bila ada) secara natural — jangan
menanyakan ulang hal yang sudah Anda ingat.

Bila user meminta berbicara dengan manusia, atau topik di luar kapasitas Anda
(negosiasi harga/kontrak, keluhan pembayaran/tagihan), atau terjadi kegagalan/frustrasi
berulang, lakukan handoff: panggil `notify_sales` untuk urusan penjualan/komersial atau
`notify_manager` untuk eskalasi/komplain, dengan `reason` yang jelas. Setelah tool sukses,
beri tahu user bahwa tim kami akan menindaklanjuti. Jangan menyatakan tim sudah dihubungi
sebelum tool benar-benar dipanggil.
```

- [ ] **Step 2: Verify the prompt imports cleanly**

Run: `uv run python -c "from app.agent.prompts import SYSTEM_PROMPT; print('remember_fact' in SYSTEM_PROMPT, 'notify_manager' in SYSTEM_PROMPT)"`
Expected: `True True`

- [ ] **Step 3: Commit**

```bash
git add app/agent/prompts.py
git commit -m "feat: memory + handoff guidance in system prompt"
```

---

## Task 7: Orchestrator — inject memory into system prompt

**Files:**
- Modify: `app/agent/orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_orchestrator.py`:

```python
def test_memory_facts_injected_into_system_prompt(session):
    from app.repositories.client_fact_repo import ClientFactRepository
    from app.repositories.user_repo import UserRepository

    user = UserRepository(session).get_or_create(phone="0873")
    session.flush()
    ClientFactRepository(session).upsert(user.id, "nama", "Budi")
    ClientFactRepository(session).upsert(user.id, "perusahaan", "Toko Maju")

    llm = FakeLLM(reply="Halo Budi!")
    handle_chat(session, llm, _FakeRetriever(), message="hai", phone="0873")

    system_sent = llm.calls[0][0]
    assert "nama: Budi" in system_sent
    assert "perusahaan: Toko Maju" in system_sent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_orchestrator.py::test_memory_facts_injected_into_system_prompt -v`
Expected: FAIL — `system_sent` is the bare `SYSTEM_PROMPT`, so `"nama: Budi"` is absent → AssertionError.

- [ ] **Step 3: Add the memory-block helper + wire it in**

In `app/agent/orchestrator.py`, add the import after the existing repository imports:

```python
from app.repositories.client_fact_repo import ClientFactRepository
```

Add this helper after the `FALLBACK_REPLY` constant:

```python
def _memory_block(facts) -> str:
    if not facts:
        return ""
    lines = "\n".join(f"- {f.key}: {f.value}" for f in facts)
    return (
        "\n\nYang sudah Anda ketahui tentang pengguna ini "
        "(dari percakapan sebelumnya):\n" + lines
    )
```

Then, inside `handle_chat`, after `user = users.get_or_create(...)` and before building `history`, add:

```python
    facts = ClientFactRepository(session).list_for_user(user.id)
    system = SYSTEM_PROMPT + _memory_block(facts)
```

And change the `llm.generate` call inside the loop from:

```python
        response = llm.generate(SYSTEM_PROMPT, convo, tools=TOOL_SPECS)
```

to:

```python
        response = llm.generate(system, convo, tools=TOOL_SPECS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_orchestrator.py::test_memory_facts_injected_into_system_prompt -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/agent/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrator injects client_facts into system prompt"
```

---

## Task 8: Orchestrator loops — remember + handoff

**Files:**
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_orchestrator.py`:

```python
def test_remember_fact_loop_persists(session):
    from app.repositories.client_fact_repo import ClientFactRepository

    scripted = [
        LLMResponse(tool_calls=[ToolCall(name="remember_fact", args={"key": "nama", "value": "Budi"})]),
        LLMResponse(text="Senang berkenalan, Budi!"),
    ]
    llm = FakeLLM(responses=scripted)
    reply, user = handle_chat(
        session, llm, _FakeRetriever(), message="nama saya Budi", phone="0874"
    )
    facts = ClientFactRepository(session).list_for_user(user.id)
    assert any(f.key == "nama" and f.value == "Budi" for f in facts)


def test_handoff_loop_persists_notification(session):
    from sqlalchemy import select

    from app.models.notification import Notification

    scripted = [
        LLMResponse(tool_calls=[ToolCall(name="notify_manager", args={"reason": "komplain pembayaran"})]),
        LLMResponse(text="Saya teruskan ke tim kami."),
    ]
    llm = FakeLLM(responses=scripted)
    reply, user = handle_chat(
        session, llm, _FakeRetriever(), message="saya mau komplain", phone="0875"
    )
    notifs = session.scalars(select(Notification)).all()
    assert len(notifs) == 1
    assert notifs[0].target_role == "manager"
    assert notifs[0].payload["phone"] == "0875"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator.py -k "remember_fact_loop or handoff_loop" -v`
Expected: PASS (2 tests). (Orchestrator already forwards `session` and `user` to `dispatch`; the new tools flow through automatically.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_orchestrator.py
git commit -m "test: orchestrator loops for remember_fact + handoff"
```

---

## Task 9: Chat API e2e — handoff wiring

**Files:**
- Modify: `tests/test_chat_api.py`

- [ ] **Step 1: Register the new models for the API test engine**

In `tests/test_chat_api.py`, add after the `Ticket` import:

```python
from app.models.client_fact import ClientFact  # noqa: F401
from app.models.notification import Notification  # noqa: F401
```

- [ ] **Step 2: Write the e2e test**

Append to `tests/test_chat_api.py`:

```python
def test_handoff_flow_via_chat(build_client):
    scripted = [
        LLMResponse(
            tool_calls=[
                ToolCall(name="notify_manager", args={"reason": "klien minta bicara dengan manusia"})
            ]
        ),
        LLMResponse(text="Baik, saya teruskan ke tim kami. Mohon ditunggu."),
    ]
    client = build_client(FakeLLM(responses=scripted), _EmptyRetriever())
    resp = client.post("/chat", json={"message": "saya mau bicara dengan orang", "phone": "0864"})
    assert resp.status_code == 200
    assert "tim" in resp.json()["reply"].lower()
```

- [ ] **Step 3: Run test to verify it passes**

Run: `uv run pytest tests/test_chat_api.py::test_handoff_flow_via_chat -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_chat_api.py
git commit -m "test: e2e chat wiring for human handoff"
```

---

## Task 10: Full suite + final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `uv run pytest -q`
Expected: all tests pass (68 prior + 8 new Sprint 6 tests = ~76 total). No failures.

- [ ] **Step 2: Confirm migration is at head**

Run: `uv run alembic current`
Expected: shows the Sprint 6 revision hash as current (head).

- [ ] **Step 3: Confirm tool registration**

Run: `uv run python -c "from app.agent.tools import TOOL_SPECS; print(sorted(t.name for t in TOOL_SPECS))"`
Expected: includes `notify_manager`, `notify_sales`, `remember_fact` alongside the prior 9 tools (12 total).

---

## Self-Review

**Spec coverage:**
- §2 Models (client_facts, notifications) → Tasks 1, 2 ✓
- §3 Repositories → Tasks 1, 2 ✓
- §4 Tools (remember_fact, notify_sales, notify_manager + `_notify` helper) → Tasks 4, 5 ✓
- §5 Orchestrator memory injection → Task 7 ✓
- §6 System prompt → Task 6 ✓
- §7 Error handling → covered by existing `try/except` in dispatch; empty-arg safety noted in remember_fact branch ✓
- §8 Testing (repo/tool/orchestrator-memory/orchestrator-loops/e2e) → Tasks 1, 2, 4, 5, 7, 8, 9 ✓
- §9 DOD → Task 10 verification ✓

**Type consistency:** `ClientFactRepository.upsert(user_id, key, value)` / `list_for_user(user_id)`; `NotificationRepository.create(target_role, *, reason, payload)`; helper `_notify(session, user, role, reason)`; orchestrator helper `_memory_block(facts)`. Tool names `remember_fact` / `notify_sales` / `notify_manager` consistent across specs, dispatch, prompts, and tests. `payload` keys (`name`/`phone`/`email`) consistent between `_notify` and tests.

**Placeholder scan:** none — every code/test/command step contains concrete content.
