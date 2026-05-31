# Sprint 1 — Chat Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Learning note:** This is a learning build. During execution, after each task, explain in **Bahasa Indonesia** how the code works (see memory `explain-implementation-in-bahasa`). The plan itself is in English; the teaching explanation is in Bahasa.

**Goal:** Stand up the FastAPI + Postgres skeleton with a working `/chat` endpoint that talks to Gemini Flash, persists the conversation (`User` + `message`), and a minimal web chat UI.

**Architecture:** Single tool-calling agent loop — but Sprint 1 has **no tools yet**, just the conversation loop. Layering: API → orchestrator → repositories → DB, with the LLM behind a swappable `LLMClient` interface. A `FakeLLM` enables deterministic tests with no API calls.

**Tech Stack:** Python 3.14, `uv`, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL (psycopg3), pydantic-settings, `google-genai` (Gemini), pytest, httpx (TestClient). Tests run on in-memory SQLite via the SQLAlchemy abstraction.

**Note on table names:** `user` is a reserved word in Postgres, so the table is named `users` (and `messages`) to keep raw `psql` queries painless. Model classes remain `User` / `Message`.

---

### Task 1: Project scaffolding & dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.python-version`
- Create: `app/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "efisien-cs"
version = "0.1.0"
description = "AI Customer Service for PT Maju Digital"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.2",
    "pydantic-settings>=2.5",
    "google-genai>=0.8",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "httpx>=0.27",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.python-version`**

```
3.14
```

- [ ] **Step 3: Create `.env.example`**

```
DATABASE_URL=postgresql+psycopg://localhost:5432/efisien_cs
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.0-flash
```

- [ ] **Step 4: Create empty package markers**

Create `app/__init__.py` and `tests/__init__.py` as empty files.

- [ ] **Step 5: Install dependencies and create the database**

Run:
```bash
uv sync
createdb efisien_cs
```
Expected: `uv sync` creates `.venv` and resolves all deps; `createdb` returns silently (DB created).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .python-version .env.example app/__init__.py tests/__init__.py
git commit -m "chore: project scaffolding and dependencies"
```

---

### Task 2: Configuration

**Files:**
- Create: `app/config.py`

- [ ] **Step 1: Create `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost:5432/efisien_cs"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"


settings = Settings()
```

- [ ] **Step 2: Verify it imports**

Run: `uv run python -c "from app.config import settings; print(settings.gemini_model)"`
Expected: prints `gemini-2.0-flash`

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "feat: app configuration via pydantic-settings"
```

---

### Task 3: Database engine, session, and Base

**Files:**
- Create: `app/models/__init__.py` (empty)
- Create: `app/models/base.py`
- Create: `app/db.py`

- [ ] **Step 1: Create `app/models/__init__.py`** (empty file)

- [ ] **Step 2: Create `app/models/base.py`**

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 3: Create `app/db.py`**

```python
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a DB session and closes it after the request."""
    with SessionLocal() as session:
        yield session
```

- [ ] **Step 4: Commit**

```bash
git add app/models/__init__.py app/models/base.py app/db.py
git commit -m "feat: database engine, session factory, and ORM base"
```

---

### Task 4: User and Message models

**Files:**
- Create: `app/models/user.py`
- Create: `app/models/message.py`

- [ ] **Step 1: Create `app/models/user.py`**

```python
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 2: Create `app/models/message.py`**

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant" | "tool"
    content: Mapped[str] = mapped_column(Text)
    tool_name: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 3: Verify models import and register on Base**

Run: `uv run python -c "from app.models.user import User; from app.models.message import Message; from app.models.base import Base; print(sorted(Base.metadata.tables))"`
Expected: prints `['messages', 'users']`

- [ ] **Step 4: Commit**

```bash
git add app/models/user.py app/models/message.py
git commit -m "feat: User and Message ORM models"
```

---

### Task 5: Alembic migrations

**Files:**
- Create: `alembic.ini`, `alembic/` (via `alembic init`)
- Modify: `alembic/env.py`
- Create: first migration under `alembic/versions/`

- [ ] **Step 1: Initialize Alembic**

Run: `uv run alembic init alembic`
Expected: creates `alembic.ini` and the `alembic/` directory.

- [ ] **Step 2: Point Alembic at our settings and metadata — edit `alembic/env.py`**

Near the top, after the existing imports, add:

```python
from app.config import settings
from app.models.base import Base
from app.models.user import User  # noqa: F401  (register table)
from app.models.message import Message  # noqa: F401  (register table)

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata
```

Replace the line `target_metadata = None` with the assignment above (remove the `None` line).

- [ ] **Step 3: Autogenerate the first migration**

Run: `uv run alembic revision --autogenerate -m "create users and messages"`
Expected: a new file in `alembic/versions/` containing `create_table('users'...)` and `create_table('messages'...)`.

- [ ] **Step 4: Apply the migration**

Run: `uv run alembic upgrade head`
Expected: `Running upgrade -> <rev>, create users and messages`. Verify with:
```bash
psql efisien_cs -c "\dt"
```
Expected: lists `users`, `messages`, `alembic_version`.

- [ ] **Step 5: Commit**

```bash
git add alembic.ini alembic/
git commit -m "feat: alembic setup and initial migration for users/messages"
```

---

### Task 6: UserRepository (match-or-create)

**Files:**
- Create: `app/repositories/__init__.py` (empty)
- Create: `app/repositories/user_repo.py`
- Test: `tests/conftest.py`, `tests/test_user_repo.py`

- [ ] **Step 1: Create `tests/conftest.py`**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.user import User  # noqa: F401  (register table)
from app.models.message import Message  # noqa: F401  (register table)


@pytest.fixture
def session() -> Session:
    """In-memory SQLite session for fast, isolated tests."""
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    with TestSession() as s:
        yield s
```

- [ ] **Step 2: Write the failing test — `tests/test_user_repo.py`**

```python
from app.repositories.user_repo import UserRepository


def test_creates_new_user_when_none_matches(session):
    repo = UserRepository(session)
    user = repo.get_or_create(name="Budi", phone="08123456789", email=None)
    session.flush()
    assert user.id is not None
    assert user.name == "Budi"
    assert user.phone == "08123456789"


def test_matches_existing_user_by_phone(session):
    repo = UserRepository(session)
    first = repo.get_or_create(name="Budi", phone="08123456789", email=None)
    session.flush()
    again = repo.get_or_create(name="Budi Updated", phone="08123456789", email=None)
    assert again.id == first.id
    assert again.name == "Budi Updated"  # name refreshed on return


def test_matches_existing_user_by_email(session):
    repo = UserRepository(session)
    first = repo.get_or_create(name="Sari", phone=None, email="sari@mail.com")
    session.flush()
    again = repo.get_or_create(name=None, phone=None, email="sari@mail.com")
    assert again.id == first.id
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_user_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.repositories.user_repo'`

- [ ] **Step 4: Create `app/repositories/__init__.py`** (empty file)

- [ ] **Step 5: Implement `app/repositories/user_repo.py`**

```python
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create(
        self,
        *,
        name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
    ) -> User:
        user: User | None = None
        if phone:
            user = self.session.scalar(select(User).where(User.phone == phone))
        if user is None and email:
            user = self.session.scalar(select(User).where(User.email == email))

        if user is None:
            user = User(name=name, phone=phone, email=email)
            self.session.add(user)
            self.session.flush()
            return user

        if name:
            user.name = name
        user.last_seen_at = datetime.now(timezone.utc)
        return user
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_user_repo.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add app/repositories/__init__.py app/repositories/user_repo.py tests/conftest.py tests/test_user_repo.py
git commit -m "feat: UserRepository with match-or-create by phone/email"
```

---

### Task 7: MessageRepository

**Files:**
- Create: `app/repositories/message_repo.py`
- Test: `tests/test_message_repo.py`

- [ ] **Step 1: Write the failing test — `tests/test_message_repo.py`**

```python
from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository


def test_add_and_fetch_recent_in_chronological_order(session):
    user = UserRepository(session).get_or_create(phone="0811")
    session.flush()
    repo = MessageRepository(session)
    repo.add(user.id, "user", "halo")
    repo.add(user.id, "assistant", "halo juga")
    repo.add(user.id, "user", "apa layanan kalian?")

    recent = repo.recent(user.id, limit=15)
    assert [m.content for m in recent] == ["halo", "halo juga", "apa layanan kalian?"]
    assert [m.role for m in recent] == ["user", "assistant", "user"]


def test_recent_respects_limit_and_keeps_latest(session):
    user = UserRepository(session).get_or_create(phone="0811")
    session.flush()
    repo = MessageRepository(session)
    for i in range(5):
        repo.add(user.id, "user", f"msg-{i}")

    recent = repo.recent(user.id, limit=2)
    assert [m.content for m in recent] == ["msg-3", "msg-4"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_message_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.repositories.message_repo'`

- [ ] **Step 3: Implement `app/repositories/message_repo.py`**

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message


class MessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        user_id: int,
        role: str,
        content: str,
        tool_name: str | None = None,
    ) -> Message:
        message = Message(
            user_id=user_id, role=role, content=content, tool_name=tool_name
        )
        self.session.add(message)
        self.session.flush()
        return message

    def recent(self, user_id: int, limit: int = 15) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        rows = list(self.session.scalars(stmt))
        return list(reversed(rows))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_message_repo.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/repositories/message_repo.py tests/test_message_repo.py
git commit -m "feat: MessageRepository with add and recent-history fetch"
```

---

### Task 8: LLM interface + FakeLLM

**Files:**
- Create: `app/llm/__init__.py` (empty)
- Create: `app/llm/base.py`
- Create: `app/llm/fake.py`
- Test: `tests/test_fake_llm.py`

- [ ] **Step 1: Create `app/llm/__init__.py`** (empty file)

- [ ] **Step 2: Create `app/llm/base.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


class LLMClient(ABC):
    @abstractmethod
    def generate(self, system: str, messages: list[ChatMessage]) -> str:
        """Return the assistant's text reply given a system prompt and history."""
        ...
```

- [ ] **Step 3: Write the failing test — `tests/test_fake_llm.py`**

```python
from app.llm.base import ChatMessage
from app.llm.fake import FakeLLM


def test_fake_llm_returns_canned_reply_and_records_input():
    llm = FakeLLM(reply="Halo! Ada yang bisa dibantu?")
    messages = [ChatMessage(role="user", content="hai")]
    out = llm.generate("SYSTEM", messages)
    assert out == "Halo! Ada yang bisa dibantu?"
    assert llm.last_system == "SYSTEM"
    assert llm.last_messages == messages
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_fake_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.llm.fake'`

- [ ] **Step 5: Implement `app/llm/fake.py`**

```python
from app.llm.base import ChatMessage, LLMClient


class FakeLLM(LLMClient):
    """Deterministic LLM for tests — no network calls."""

    def __init__(self, reply: str = "Halo! Ada yang bisa saya bantu?") -> None:
        self.reply = reply
        self.last_system: str | None = None
        self.last_messages: list[ChatMessage] | None = None

    def generate(self, system: str, messages: list[ChatMessage]) -> str:
        self.last_system = system
        self.last_messages = messages
        return self.reply
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_fake_llm.py -v`
Expected: 1 passed

- [ ] **Step 7: Commit**

```bash
git add app/llm/__init__.py app/llm/base.py app/llm/fake.py tests/test_fake_llm.py
git commit -m "feat: LLMClient interface and FakeLLM for tests"
```

---

### Task 9: Gemini LLM implementation

**Files:**
- Create: `app/llm/gemini.py`

> No unit test (it calls the real API). It's exercised manually in Task 13's smoke test.

- [ ] **Step 1: Implement `app/llm/gemini.py`**

```python
from google import genai
from google.genai import types

from app.config import settings
from app.llm.base import ChatMessage, LLMClient


class GeminiLLM(LLMClient):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.client = genai.Client(api_key=api_key or settings.gemini_api_key)
        self.model = model or settings.gemini_model

    def generate(self, system: str, messages: list[ChatMessage]) -> str:
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part.from_text(text=m.content)],
            )
            for m in messages
        ]
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        return response.text or ""
```

- [ ] **Step 2: Verify it imports**

Run: `uv run python -c "from app.llm.gemini import GeminiLLM; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add app/llm/gemini.py
git commit -m "feat: Gemini Flash LLM client"
```

---

### Task 10: System prompt

**Files:**
- Create: `app/agent/__init__.py` (empty)
- Create: `app/agent/prompts.py`

- [ ] **Step 1: Create `app/agent/__init__.py`** (empty file)

- [ ] **Step 2: Create `app/agent/prompts.py`**

```python
SYSTEM_PROMPT = """Anda adalah asisten Customer Service AI untuk PT Maju Digital,
sebuah software house yang menyediakan jasa pembuatan Website, Mobile App, ERP,
HRIS, Sistem Kasir (POS), dan Sistem Custom.

Peran Anda:
- Menjawab pertanyaan calon klien maupun klien yang sudah ada dengan ramah dan profesional.
- Selalu menjawab dalam Bahasa Indonesia, singkat, jelas, dan membantu.
- Jika belum tahu jawabannya, katakan dengan jujur dan tawarkan untuk menghubungkan
  dengan tim manusia.

Pada tahap ini Anda hanya melakukan percakapan biasa (belum ada akses ke data atau
tool). Kemampuan lain akan ditambahkan kemudian.
"""
```

- [ ] **Step 3: Commit**

```bash
git add app/agent/__init__.py app/agent/prompts.py
git commit -m "feat: Indonesian system prompt for the CS agent"
```

---

### Task 11: Agent orchestrator (chat loop, no tools)

**Files:**
- Create: `app/agent/orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test — `tests/test_orchestrator.py`**

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
    assert user.id is not None

    stored = MessageRepository(session).recent(user.id, limit=10)
    assert [(m.role, m.content) for m in stored] == [
        ("user", "Apa saja layanan kalian?"),
        ("assistant", "Tentu, kami menyediakan banyak layanan."),
    ]


def test_handle_chat_sends_prior_history_to_llm(session):
    llm = FakeLLM(reply="ok")
    handle_chat(session, llm, message="pesan pertama", phone="0811")
    handle_chat(session, llm, message="pesan kedua", phone="0811")

    # On the second turn the LLM should have received the prior turns + new message.
    contents = [m.content for m in llm.last_messages]
    assert contents == ["pesan pertama", "ok", "pesan kedua"]
    assert llm.last_system.startswith("Anda adalah asisten Customer Service AI")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.orchestrator'`

- [ ] **Step 3: Implement `app/agent/orchestrator.py`**

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

    reply = llm.generate(SYSTEM_PROMPT, llm_messages)

    messages.add(user.id, "user", message)
    messages.add(user.id, "assistant", reply)
    session.commit()

    return reply, user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/agent/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: chat orchestrator loop (no tools yet)"
```

---

### Task 12: /chat and /health API

**Files:**
- Create: `app/schemas/__init__.py` (empty)
- Create: `app/schemas/chat.py`
- Create: `app/api/__init__.py` (empty)
- Create: `app/api/chat.py`
- Create: `app/main.py`
- Test: `tests/test_chat_api.py`

- [ ] **Step 1: Create `app/schemas/__init__.py`** (empty) and `app/schemas/chat.py`**

```python
from pydantic import BaseModel, model_validator


class ChatRequest(BaseModel):
    message: str
    name: str | None = None
    phone: str | None = None
    email: str | None = None

    @model_validator(mode="after")
    def require_identity(self):
        if not self.phone and not self.email:
            raise ValueError("phone or email is required")
        return self


class ChatResponse(BaseModel):
    reply: str
    user_id: int
```

- [ ] **Step 2: Create `app/api/__init__.py`** (empty) and `app/api/chat.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.orchestrator import handle_chat
from app.db import get_session
from app.llm.base import LLMClient
from app.llm.gemini import GeminiLLM
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


def get_llm() -> LLMClient:
    return GeminiLLM()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    session: Session = Depends(get_session),
    llm: LLMClient = Depends(get_llm),
) -> ChatResponse:
    reply, user = handle_chat(
        session,
        llm,
        message=req.message,
        name=req.name,
        phone=req.phone,
        email=req.email,
    )
    return ChatResponse(reply=reply, user_id=user.id)
```

- [ ] **Step 3: Create `app/main.py`**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.chat import router

app = FastAPI(title="Efisien CS")
app.include_router(router)
# Explicit API routes above take precedence; this serves the chat UI at "/".
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

- [ ] **Step 4: Write the failing test — `tests/test_chat_api.py`**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chat import get_llm
from app.db import get_session
from app.llm.fake import FakeLLM
from app.main import app
from app.models.base import Base
from app.models.user import User  # noqa: F401
from app.models.message import Message  # noqa: F401


@pytest.fixture
def client():
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
    app.dependency_overrides[get_llm] = lambda: FakeLLM(reply="Halo dari AI")
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_chat_endpoint_returns_reply(client):
    resp = client.post("/chat", json={"message": "hai", "phone": "0811"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Halo dari AI"
    assert body["user_id"] >= 1


def test_chat_endpoint_requires_identity(client):
    resp = client.post("/chat", json={"message": "hai"})
    assert resp.status_code == 422


def test_health_endpoint(client):
    assert client.get("/health").json() == {"status": "ok"}
```

- [ ] **Step 5: Run test to verify it fails**

Run: `uv run pytest tests/test_chat_api.py -v`
Expected: FAIL — collection error (`static` directory missing) or import error. This is expected; Task 13 creates `static/`. To unblock now, create an empty dir: `mkdir -p static`. Re-run; tests should now fail on the missing endpoints/modules instead.

- [ ] **Step 6: Run the full suite to verify everything passes**

Run: `uv run pytest -v`
Expected: all tests pass (user_repo 3, message_repo 2, fake_llm 1, orchestrator 2, chat_api 3).

- [ ] **Step 7: Commit**

```bash
git add app/schemas app/api app/main.py tests/test_chat_api.py
git commit -m "feat: /chat and /health endpoints with FakeLLM-overridable deps"
```

---

### Task 13: Minimal web chat UI + manual smoke test

**Files:**
- Create: `static/index.html`

- [ ] **Step 1: Create `static/index.html`**

```html
<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Efisien CS — PT Maju Digital</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
    #log { border: 1px solid #ccc; border-radius: 8px; padding: 1rem; height: 360px; overflow-y: auto; }
    .msg { margin: .4rem 0; }
    .user { text-align: right; color: #1a73e8; }
    .ai { text-align: left; color: #202124; }
    form { display: flex; gap: .5rem; margin-top: .75rem; }
    input[type=text] { flex: 1; padding: .6rem; }
    button { padding: .6rem 1rem; }
    .ident { display: flex; gap: .5rem; margin-bottom: .75rem; }
  </style>
</head>
<body>
  <h2>AI Customer Service — PT Maju Digital</h2>
  <div class="ident">
    <input id="name" type="text" placeholder="Nama" />
    <input id="phone" type="text" placeholder="No. HP (mis. 08123...)" />
  </div>
  <div id="log"></div>
  <form id="form">
    <input id="message" type="text" placeholder="Tulis pesan..." autocomplete="off" required />
    <button type="submit">Kirim</button>
  </form>

  <script>
    const log = document.getElementById("log");
    function add(text, cls) {
      const div = document.createElement("div");
      div.className = "msg " + cls;
      div.textContent = text;
      log.appendChild(div);
      log.scrollTop = log.scrollHeight;
    }
    document.getElementById("form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const message = document.getElementById("message").value.trim();
      const name = document.getElementById("name").value.trim();
      const phone = document.getElementById("phone").value.trim();
      if (!message) return;
      if (!phone) { add("Mohon isi No. HP dulu.", "ai"); return; }
      add(message, "user");
      document.getElementById("message").value = "";
      try {
        const res = await fetch("/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message, name: name || null, phone }),
        });
        const data = await res.json();
        add(data.reply ?? "(tidak ada balasan)", "ai");
      } catch (err) {
        add("Terjadi kesalahan koneksi.", "ai");
      }
    });
  </script>
</body>
</html>
```

- [ ] **Step 2: Run the server and smoke-test against real Gemini**

First set your real key in `.env` (copy from `.env.example`, fill `GEMINI_API_KEY`). Then run:
```bash
uv run uvicorn app.main:app --reload
```
Expected: server starts on `http://127.0.0.1:8000`.

- [ ] **Step 3: Verify the health endpoint**

Run: `curl -s http://127.0.0.1:8000/health`
Expected: `{"status":"ok"}`

- [ ] **Step 4: Verify chat end-to-end in the browser**

Open `http://127.0.0.1:8000/`, enter a phone number, send "Apa saja layanan PT Maju Digital?".
Expected: a coherent Indonesian reply from Gemini. Then check persistence:
```bash
psql efisien_cs -c "SELECT role, left(content,40) FROM messages ORDER BY id;"
```
Expected: rows for your `user` message and the `assistant` reply.

- [ ] **Step 5: Commit**

```bash
git add static/index.html
git commit -m "feat: minimal web chat UI and Sprint 1 smoke test"
```

---

## Sprint 1 Done When
- `uv run pytest` is green (11 tests).
- `uvicorn` serves the chat page, a browser message gets a real Gemini reply in Indonesian, and both messages persist in Postgres.
- The conversation loop, layering (API → orchestrator → repo → DB), and swappable `LLMClient` are in place — ready for Sprint 2 (RAG + the `search_knowledge_base` tool).
