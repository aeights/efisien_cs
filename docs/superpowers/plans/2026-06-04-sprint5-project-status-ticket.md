# Sprint 5 — Project Status + Support Ticket Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tambahkan kemampuan AI CS untuk mengecek status proyek klien existing dan membuat + menugaskan tiket support, lewat tiga tool baru (`get_project_status`, `create_ticket`, `assign_developer`).

**Architecture:** Lean — tanpa service layer. Repository dipanggil langsung dari `dispatch`. Identitas user di-inject dari context (bukan argumen LLM). Dua model baru (`projects`, `tickets`) + repository masing-masing. Satu migration Alembic. Seed script untuk data proyek demo. TDD penuh dengan SQLite in-memory + FakeLLM.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL (prod) / SQLite in-memory (test), pytest, `uv`.

---

## File Structure

| File | Tanggung jawab |
|---|---|
| `app/models/project.py` (create) | ORM model `projects` |
| `app/models/ticket.py` (create) | ORM model `tickets` |
| `app/repositories/project_repo.py` (create) | akses data proyek |
| `app/repositories/ticket_repo.py` (create) | akses data tiket |
| `app/agent/tools.py` (modify) | 3 ToolSpec + 3 cabang dispatch baru |
| `app/agent/prompts.py` (modify) | alur status proyek + tiket di system prompt |
| `alembic/versions/<new>.py` (create) | migration projects + tickets |
| `alembic/env.py` (modify) | register model baru |
| `scripts/seed_projects.py` (create) | seed proyek demo (idempoten) |
| `tests/conftest.py` (modify) | import model baru agar tabel dibuat |
| `tests/test_project_repo.py` (create) | unit test ProjectRepository |
| `tests/test_ticket_repo.py` (create) | unit test TicketRepository |
| `tests/test_tools.py` (modify) | test 3 tool baru |
| `tests/test_orchestrator.py` (modify) | test loop alur tiket |
| `tests/test_chat_api.py` (modify) | e2e wiring alur tiket + status proyek |

Catatan: test e2e di `test_chat_api.py` hanya memverifikasi wiring (endpoint 200 + reply ter-script), karena `FakeLLM` mengabaikan hasil tool. Kebenaran data dibuktikan di level unit tool/repo dan orchestrator (yang punya akses langsung ke session).

---

## Task 1: Project model + ProjectRepository

**Files:**
- Create: `app/models/project.py`
- Create: `app/repositories/project_repo.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_project_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_project_repo.py`:

```python
from app.models.user import User
from app.repositories.project_repo import ProjectRepository


def _user(session):
    u = User(name="Klien", phone="0850")
    session.add(u)
    session.flush()
    return u


def test_create_and_list_for_user(session):
    u = _user(session)
    repo = ProjectRepository(session)
    repo.create(
        u.id, name="POS Toko A", type="POS", progress=60,
        status="in_progress", details={"backend": "done"},
    )
    repo.create(u.id, name="Website Profil", type="Website", progress=20)
    projects = repo.list_for_user(u.id)
    assert [p.name for p in projects] == ["POS Toko A", "Website Profil"]
    assert projects[0].progress == 60
    assert projects[0].details == {"backend": "done"}
    assert projects[1].status == "in_progress"


def test_list_for_user_empty(session):
    u = _user(session)
    assert ProjectRepository(session).list_for_user(u.id) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_project_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.repositories.project_repo'`

- [ ] **Step 3: Create the model**

Create `app/models/project.py`:

```python
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(120))
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(
        String(16), default="in_progress", server_default="in_progress"
    )
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 4: Register the model in conftest**

In `tests/conftest.py`, add after the `Meeting` import (line 10):

```python
from app.models.project import Project  # noqa: F401  (register table)
```

- [ ] **Step 5: Create the repository**

Create `app/repositories/project_repo.py`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        client_id: int,
        *,
        name: str,
        type: str,
        progress: int = 0,
        status: str = "in_progress",
        details: dict | None = None,
    ) -> Project:
        project = Project(
            client_id=client_id,
            name=name,
            type=type,
            progress=progress,
            status=status,
            details=details,
        )
        self.session.add(project)
        self.session.flush()
        return project

    def list_for_user(self, user_id: int) -> list[Project]:
        return list(
            self.session.scalars(
                select(Project).where(Project.client_id == user_id).order_by(Project.id)
            )
        )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_project_repo.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add app/models/project.py app/repositories/project_repo.py tests/conftest.py tests/test_project_repo.py
git commit -m "feat: Project model + ProjectRepository (create, list_for_user)"
```

---

## Task 2: Ticket model + TicketRepository

**Files:**
- Create: `app/models/ticket.py`
- Create: `app/repositories/ticket_repo.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_ticket_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ticket_repo.py`:

```python
from app.models.user import User
from app.repositories.ticket_repo import TicketRepository


def _user(session):
    u = User(name="Klien", phone="0851")
    session.add(u)
    session.flush()
    return u


def test_create_ticket_defaults_open(session):
    u = _user(session)
    t = TicketRepository(session).create(
        u.id, description="tidak bisa login", category="bug", priority="high"
    )
    assert t.status == "open"
    assert t.project_id is None
    assert t.category == "bug"
    assert t.assigned_developer is None


def test_get_latest_for_user(session):
    u = _user(session)
    repo = TicketRepository(session)
    repo.create(u.id, description="a", category="question", priority="low")
    repo.create(u.id, description="b", category="bug", priority="high")
    latest = repo.get_latest_for_user(u.id)
    assert latest.description == "b"


def test_assign_sets_status_and_developer(session):
    u = _user(session)
    repo = TicketRepository(session)
    t = repo.create(u.id, description="x", category="bug", priority="med")
    repo.assign(t)
    assert t.status == "assigned"
    assert t.assigned_developer == "Tim Development"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ticket_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.repositories.ticket_repo'`

- [ ] **Step 3: Create the model**

Create `app/models/ticket.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    category: Mapped[str] = mapped_column(String(16))  # bug/feature/question
    priority: Mapped[str] = mapped_column(String(8))  # low/med/high
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open")
    description: Mapped[str] = mapped_column(String(500))
    assigned_developer: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 4: Register the model in conftest**

In `tests/conftest.py`, add after the `Project` import from Task 1:

```python
from app.models.ticket import Ticket  # noqa: F401  (register table)
```

- [ ] **Step 5: Create the repository**

Create `app/repositories/ticket_repo.py`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket


class TicketRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        user_id: int,
        *,
        description: str,
        category: str,
        priority: str,
        project_id: int | None = None,
    ) -> Ticket:
        ticket = Ticket(
            user_id=user_id,
            description=description,
            category=category,
            priority=priority,
            project_id=project_id,
            status="open",
        )
        self.session.add(ticket)
        self.session.flush()
        return ticket

    def get_latest_for_user(self, user_id: int) -> Ticket | None:
        return self.session.scalar(
            select(Ticket).where(Ticket.user_id == user_id).order_by(Ticket.id.desc())
        )

    def assign(self, ticket: Ticket, *, developer: str = "Tim Development") -> Ticket:
        ticket.status = "assigned"
        ticket.assigned_developer = developer
        self.session.flush()
        return ticket
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_ticket_repo.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add app/models/ticket.py app/repositories/ticket_repo.py tests/conftest.py tests/test_ticket_repo.py
git commit -m "feat: Ticket model + TicketRepository (create, get_latest_for_user, assign)"
```

---

## Task 3: Alembic migration (projects + tickets)

**Files:**
- Modify: `alembic/env.py`
- Create: `alembic/versions/<generated>.py`

**Prasyarat:** PostgreSQL (Postgres.app) harus menyala untuk `alembic upgrade head`. DB: `efisien_cs`.

- [ ] **Step 1: Register models in alembic env**

In `alembic/env.py`, add after the `Meeting` import (line 24):

```python
from app.models.project import Project  # noqa: F401  (register table)
from app.models.ticket import Ticket  # noqa: F401  (register table)
```

- [ ] **Step 2: Create an empty revision**

Run: `uv run alembic revision -m "create projects and tickets"`
Expected: prints `Generating .../alembic/versions/<hash>_create_projects_and_tickets.py`. The new file's `down_revision` is auto-set to `'2e298145de06'`.

- [ ] **Step 3: Fill in upgrade/downgrade**

Open the newly created file and replace the `upgrade()` and `downgrade()` bodies with:

```python
def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=120), nullable=False),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="in_progress", nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_client_id"), "projects", ["client_id"], unique=False)
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("assigned_developer", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tickets_user_id"), "tickets", ["user_id"], unique=False)
    op.create_index(op.f("ix_tickets_project_id"), "tickets", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tickets_project_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_user_id"), table_name="tickets")
    op.drop_table("tickets")
    op.drop_index(op.f("ix_projects_client_id"), table_name="projects")
    op.drop_table("projects")
```

- [ ] **Step 4: Apply the migration**

Run: `uv run alembic upgrade head`
Expected: `Running upgrade 2e298145de06 -> <hash>, create projects and tickets`. No errors.

- [ ] **Step 5: Verify the schema**

Run: `psql efisien_cs -c "\d tickets" -c "\d projects"`
Expected: both tables exist with the columns above; `tickets.project_id` is nullable, `tickets.user_id` NOT NULL.

- [ ] **Step 6: Commit**

```bash
git add alembic/env.py alembic/versions/
git commit -m "feat: add projects + tickets tables (migration)"
```

---

## Task 4: get_project_status tool

**Files:**
- Modify: `app/agent/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tools.py`:

```python
from app.repositories.project_repo import ProjectRepository
from app.repositories.ticket_repo import TicketRepository


def test_dispatch_get_project_status_empty(session):
    user = _seed_user(session, phone="0830")
    out = json.loads(
        dispatch(ToolCall(name="get_project_status", args={}), session=session, user=user)
    )
    assert "Belum ada proyek" in out["result"]


def test_dispatch_get_project_status_returns_projects(session):
    user = _seed_user(session, phone="0831")
    ProjectRepository(session).create(
        user.id, name="POS Toko A", type="POS", progress=70,
        status="in_progress", details={"frontend": 80},
    )
    out = json.loads(
        dispatch(ToolCall(name="get_project_status", args={}), session=session, user=user)
    )
    assert out["projects"][0]["name"] == "POS Toko A"
    assert out["projects"][0]["progress"] == 70
    assert out["projects"][0]["details"] == {"frontend": 80}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py::test_dispatch_get_project_status_returns_projects -v`
Expected: FAIL — dispatch returns `{"error": "Tool tidak dikenal: get_project_status"}`, so `out["projects"]` raises KeyError.

- [ ] **Step 3: Add the ToolSpec**

In `app/agent/tools.py`, add the import near the existing repo imports (after line 7):

```python
from app.repositories.project_repo import ProjectRepository
from app.repositories.ticket_repo import TicketRepository
```

Add this `ToolSpec` to the `TOOL_SPECS` list (after the `send_invitation` spec, before the closing `]`):

```python
    ToolSpec(
        name="get_project_status",
        description=(
            "Lihat status dan progres proyek milik klien yang sedang chat. "
            "Panggil saat klien existing menanyakan perkembangan proyeknya."
        ),
        parameters={"type": "object", "properties": {}},
    ),
```

- [ ] **Step 4: Add the dispatch branch**

In `app/agent/tools.py`, add this branch inside `dispatch` (after the `send_invitation` branch, before the final unknown-tool `return`):

```python
        if tool_call.name == "get_project_status":
            projects = ProjectRepository(session).list_for_user(user.id)
            if not projects:
                return json.dumps(
                    {"result": "Belum ada proyek terdaftar atas nama Anda."},
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "projects": [
                        {
                            "name": p.name,
                            "type": p.type,
                            "progress": p.progress,
                            "status": p.status,
                            "details": p.details,
                        }
                        for p in projects
                    ]
                },
                ensure_ascii=False,
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py -k project_status -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add app/agent/tools.py tests/test_tools.py
git commit -m "feat: get_project_status tool"
```

---

## Task 5: create_ticket tool

**Files:**
- Modify: `app/agent/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tools.py`:

```python
def test_dispatch_create_ticket_injects_user_and_links_project(session):
    user = _seed_user(session, phone="0832")
    project = ProjectRepository(session).create(user.id, name="Web", type="Website")
    out = json.loads(
        dispatch(
            ToolCall(
                name="create_ticket",
                args={"description": "tidak bisa login", "category": "bug", "priority": "high"},
            ),
            session=session,
            user=user,
        )
    )
    assert out["status"] == "open"
    assert out["category"] == "bug"
    assert out["priority"] == "high"
    assert out["project_id"] == project.id
    ticket = TicketRepository(session).get_latest_for_user(user.id)
    assert ticket.user_id == user.id
    assert ticket.description == "tidak bisa login"


def test_dispatch_create_ticket_invalid_enum_falls_back(session):
    user = _seed_user(session, phone="0833")
    out = json.loads(
        dispatch(
            ToolCall(
                name="create_ticket",
                args={"description": "x", "category": "wut", "priority": "urgent"},
            ),
            session=session,
            user=user,
        )
    )
    assert out["category"] == "question"
    assert out["priority"] == "med"
    assert out["project_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py -k create_ticket -v`
Expected: FAIL — unknown tool error → KeyError on `out["status"]`.

- [ ] **Step 3: Add validation constants**

In `app/agent/tools.py`, add after the `_meeting_link` function:

```python
_CATEGORIES = {"bug", "feature", "question"}
_PRIORITIES = {"low", "med", "high"}
```

- [ ] **Step 4: Add the ToolSpec**

Add this `ToolSpec` to `TOOL_SPECS` (after the `get_project_status` spec):

```python
    ToolSpec(
        name="create_ticket",
        description=(
            "Buat tiket support untuk klien existing yang melaporkan masalah atau "
            "permintaan. Tentukan category (bug/feature/question) dan priority "
            "(low/med/high) dari isi keluhan. Panggil setelah deskripsi masalah jelas."
        ),
        parameters={
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Ringkasan masalah atau permintaan klien",
                },
                "category": {
                    "type": "string",
                    "enum": ["bug", "feature", "question"],
                    "description": "Jenis tiket",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "med", "high"],
                    "description": "Tingkat prioritas",
                },
            },
            "required": ["description"],
        },
    ),
```

- [ ] **Step 5: Add the dispatch branch**

Add this branch inside `dispatch` (after the `get_project_status` branch):

```python
        if tool_call.name == "create_ticket":
            description = tool_call.args.get("description", "")
            category = tool_call.args.get("category")
            if category not in _CATEGORIES:
                category = "question"
            priority = tool_call.args.get("priority")
            if priority not in _PRIORITIES:
                priority = "med"
            projects = ProjectRepository(session).list_for_user(user.id)
            project_id = projects[-1].id if projects else None
            ticket = TicketRepository(session).create(
                user.id,
                description=description,
                category=category,
                priority=priority,
                project_id=project_id,
            )
            return json.dumps(
                {
                    "ticket_id": ticket.id,
                    "category": ticket.category,
                    "priority": ticket.priority,
                    "status": ticket.status,
                    "project_id": ticket.project_id,
                },
                ensure_ascii=False,
            )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py -k create_ticket -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add app/agent/tools.py tests/test_tools.py
git commit -m "feat: create_ticket tool (inject user, auto-link project, validate enums)"
```

---

## Task 6: assign_developer tool

**Files:**
- Modify: `app/agent/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tools.py`:

```python
def test_dispatch_assign_developer_sets_assigned(session):
    user = _seed_user(session, phone="0834")
    TicketRepository(session).create(
        user.id, description="x", category="bug", priority="med"
    )
    out = json.loads(
        dispatch(ToolCall(name="assign_developer", args={}), session=session, user=user)
    )
    assert out["status"] == "assigned"
    assert out["assigned_developer"] == "Tim Development"


def test_dispatch_assign_developer_no_ticket(session):
    user = _seed_user(session, phone="0835")
    out = json.loads(
        dispatch(ToolCall(name="assign_developer", args={}), session=session, user=user)
    )
    assert "Belum ada tiket" in out["result"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py -k assign_developer -v`
Expected: FAIL — unknown tool error.

- [ ] **Step 3: Add the ToolSpec**

Add this `ToolSpec` to `TOOL_SPECS` (after the `create_ticket` spec):

```python
    ToolSpec(
        name="assign_developer",
        description=(
            "Tugaskan tiket terbaru milik klien ke tim developer (ubah status "
            "menjadi 'assigned'). Panggil setelah create_ticket berhasil."
        ),
        parameters={"type": "object", "properties": {}},
    ),
```

- [ ] **Step 4: Add the dispatch branch**

Add this branch inside `dispatch` (after the `create_ticket` branch):

```python
        if tool_call.name == "assign_developer":
            ticket = TicketRepository(session).get_latest_for_user(user.id)
            if ticket is None:
                return json.dumps(
                    {"result": "Belum ada tiket untuk ditugaskan."}, ensure_ascii=False
                )
            TicketRepository(session).assign(ticket)
            print(
                f"[ASSIGN] Tiket #{ticket.id} ({ticket.priority}/{ticket.category}) "
                f"ditugaskan ke {ticket.assigned_developer}"
            )
            return json.dumps(
                {
                    "ticket_id": ticket.id,
                    "status": ticket.status,
                    "assigned_developer": ticket.assigned_developer,
                },
                ensure_ascii=False,
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py -k assign_developer -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add app/agent/tools.py tests/test_tools.py
git commit -m "feat: assign_developer tool (status open->assigned + console log)"
```

---

## Task 7: System prompt — status & ticket flows

**Files:**
- Modify: `app/agent/prompts.py`
- Test: `tests/test_orchestrator.py` (covered in Task 8)

- [ ] **Step 1: Add the flow guidance**

In `app/agent/prompts.py`, insert the following two paragraphs **before** the final `PENTING:` paragraph (i.e., between the meeting-booking paragraph and the anti-hallucination paragraph):

```python
Bila klien yang sudah ada menanyakan status atau progres proyeknya, panggil
`get_project_status` dan ringkas hasilnya (nama proyek, jenis, progres, status).

Bila klien melaporkan masalah, bug, atau permintaan fitur, gali deskripsi singkatnya
lalu tentukan sendiri `category` (bug/feature/question) dan `priority` (low/med/high)
berdasarkan isi keluhan. Panggil `create_ticket` untuk mencatatnya, lalu panggil
`assign_developer` agar tiket diteruskan ke tim. Setelah itu, beri tahu user bahwa
tiket sudah dibuat dan ditugaskan, sebutkan nomor tiketnya.
```

- [ ] **Step 2: Extend the anti-hallucination rule**

In the final `PENTING:` paragraph, change the parenthetical tool list to also cover tickets. Replace:

```python
sebelum tool terkait (`create_lead`/`create_meeting`) benar-benar dipanggil dan
```

with:

```python
sebelum tool terkait (`create_lead`/`create_meeting`/`create_ticket`/`assign_developer`)
benar-benar dipanggil dan
```

- [ ] **Step 3: Verify the prompt still imports cleanly**

Run: `uv run python -c "from app.agent.prompts import SYSTEM_PROMPT; print('get_project_status' in SYSTEM_PROMPT, 'create_ticket' in SYSTEM_PROMPT)"`
Expected: `True True`

- [ ] **Step 4: Commit**

```bash
git add app/agent/prompts.py
git commit -m "feat: project-status + ticket flows in system prompt"
```

---

## Task 8: Orchestrator loop — ticket flow

**Files:**
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_orchestrator.py`:

```python
def test_ticket_loop_creates_and_assigns(session):
    from app.repositories.ticket_repo import TicketRepository

    scripted = [
        LLMResponse(
            tool_calls=[
                ToolCall(
                    name="create_ticket",
                    args={"description": "tidak bisa login", "category": "bug", "priority": "high"},
                )
            ]
        ),
        LLMResponse(tool_calls=[ToolCall(name="assign_developer", args={})]),
        LLMResponse(text="Tiket Anda sudah dibuat dan ditugaskan ke tim kami."),
    ]
    llm = FakeLLM(responses=scripted)
    reply, user = handle_chat(
        session, llm, _FakeRetriever(), message="aplikasi saya error", phone="0860"
    )
    assert "ditugaskan" in reply
    ticket = TicketRepository(session).get_latest_for_user(user.id)
    assert ticket is not None
    assert ticket.status == "assigned"
    assert ticket.category == "bug"
    assert ticket.assigned_developer == "Tim Development"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_orchestrator.py::test_ticket_loop_creates_and_assigns -v`
Expected: PASS. (Orchestrator already forwards `session` and `user` to `dispatch`; no orchestrator change is needed — the tools registered in `TOOL_SPECS` flow through automatically.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_orchestrator.py
git commit -m "test: orchestrator loop for ticket create+assign"
```

---

## Task 9: Chat API e2e — ticket + project status wiring

**Files:**
- Modify: `tests/test_chat_api.py`

- [ ] **Step 1: Register the new models for the API test engine**

In `tests/test_chat_api.py`, add after the `Meeting` import (line 16):

```python
from app.models.project import Project  # noqa: F401
from app.models.ticket import Ticket  # noqa: F401
```

- [ ] **Step 2: Write the e2e tests**

Append to `tests/test_chat_api.py`:

```python
def test_ticket_flow_via_chat(build_client):
    scripted = [
        LLMResponse(
            tool_calls=[
                ToolCall(
                    name="create_ticket",
                    args={"description": "error login", "category": "bug", "priority": "high"},
                )
            ]
        ),
        LLMResponse(tool_calls=[ToolCall(name="assign_developer", args={})]),
        LLMResponse(text="Tiket Anda sudah dibuat dan ditugaskan."),
    ]
    client = build_client(FakeLLM(responses=scripted), _EmptyRetriever())
    resp = client.post("/chat", json={"message": "aplikasi error", "phone": "0861"})
    assert resp.status_code == 200
    assert "ditugaskan" in resp.json()["reply"]


def test_project_status_flow_via_chat(build_client):
    scripted = [
        LLMResponse(tool_calls=[ToolCall(name="get_project_status", args={})]),
        LLMResponse(text="Status proyek Anda sudah saya cek."),
    ]
    client = build_client(FakeLLM(responses=scripted), _EmptyRetriever())
    resp = client.post("/chat", json={"message": "gimana proyek saya?", "phone": "0862"})
    assert resp.status_code == 200
    assert "proyek" in resp.json()["reply"].lower()
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/test_chat_api.py -k "ticket_flow or project_status" -v`
Expected: PASS (2 tests)

- [ ] **Step 4: Commit**

```bash
git add tests/test_chat_api.py
git commit -m "test: e2e chat wiring for ticket + project status"
```

---

## Task 10: Seed script for demo projects

**Files:**
- Create: `scripts/seed_projects.py`

- [ ] **Step 1: Write the seed script**

Create `scripts/seed_projects.py`:

```python
import pathlib
import sys

# Allow running as `python scripts/seed_projects.py` from the project root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.repositories.project_repo import ProjectRepository  # noqa: E402
from app.repositories.user_repo import UserRepository  # noqa: E402

DEMO_PHONE = "081234567890"


def main() -> None:
    with SessionLocal() as session:
        user = UserRepository(session).get_or_create(name="Klien Demo", phone=DEMO_PHONE)
        session.flush()
        repo = ProjectRepository(session)
        if repo.list_for_user(user.id):
            print(f"Proyek demo untuk {DEMO_PHONE} sudah ada, lewati.")
            return
        repo.create(
            user.id,
            name="Aplikasi POS Toko Maju",
            type="POS",
            progress=75,
            status="in_progress",
            details={"backend": "done", "frontend": 80, "testing": "in progress"},
        )
        repo.create(
            user.id,
            name="Website Company Profile",
            type="Website",
            progress=100,
            status="completed",
        )
        session.commit()
        print(f"Seed selesai: 2 proyek untuk user id={user.id} ({DEMO_PHONE}).")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the seed script (needs Postgres running)**

Run: `uv run python scripts/seed_projects.py`
Expected: `Seed selesai: 2 proyek untuk user id=<n> (081234567890).`

- [ ] **Step 3: Verify idempotency**

Run: `uv run python scripts/seed_projects.py`
Expected: `Proyek demo untuk 081234567890 sudah ada, lewati.`

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_projects.py
git commit -m "feat: seed_projects script (idempotent demo data)"
```

---

## Task 11: Full suite + final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `uv run pytest -q`
Expected: all tests pass (54 prior + new Sprint 5 tests, ~67 total). No failures.

- [ ] **Step 2: Confirm migration is at head**

Run: `uv run alembic current`
Expected: shows the Sprint 5 revision hash as current (head).

- [ ] **Step 3: Confirm tool registration**

Run: `uv run python -c "from app.agent.tools import TOOL_SPECS; print(sorted(t.name for t in TOOL_SPECS))"`
Expected: includes `assign_developer`, `create_ticket`, `get_project_status` alongside the prior 6 tools (9 total).

---

## Self-Review

**Spec coverage:**
- §2 Models → Tasks 1, 2 ✓
- §3 Repositories → Tasks 1, 2 ✓
- §4 Tools (3) → Tasks 4, 5, 6 ✓
- §5 System prompt → Task 7 ✓
- §6 Migration + seed → Tasks 3, 10 ✓
- §7 Error handling → enum fallback (Task 5), no-data messages (Tasks 4, 6) ✓
- §8 Testing (repo/tool/orchestrator/e2e) → Tasks 1, 2, 4, 5, 6, 8, 9 ✓
- §9 DOD → covered by Task 11 verification ✓

**Type consistency:** `ProjectRepository.create(client_id, *, name, type, progress, status, details)` / `list_for_user(user_id)`; `TicketRepository.create(user_id, *, description, category, priority, project_id)` / `get_latest_for_user(user_id)` / `assign(ticket, *, developer)` — used identically across tools, tests, and seed script. Tool names `get_project_status` / `create_ticket` / `assign_developer` consistent across specs, dispatch, prompts, and tests.

**Placeholder scan:** none — every code/test/command step contains concrete content.
