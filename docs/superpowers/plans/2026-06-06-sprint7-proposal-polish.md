# Sprint 7 — Proposal Generation + Polish (final) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tambahkan tool `generate_proposal` (LLM mengisi scope/timeline/cost/deliverables lewat skema tool, kode menyimpan ke `lead.proposal` + menandai lead `qualified`), plus polish: perbaikan branding UI dan full-workflow acceptance test.

**Architecture:** Lean — tanpa service layer, tanpa model/migration baru (kolom `lead.proposal` JSON sudah ada sejak Sprint 3). Repository `LeadRepository` ditambah `set_proposal`. Tool baru di `dispatch`, identitas user di-inject. Structured output via skema tool (Gemini mengisi argumen). TDD dengan SQLite in-memory + FakeLLM.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.0, PostgreSQL (prod) / SQLite (test), pytest, `uv`.

---

## File Structure

| File | Tanggung jawab |
|---|---|
| `app/repositories/lead_repo.py` (modify) | tambah `set_proposal(lead, proposal)` |
| `app/agent/tools.py` (modify) | ToolSpec + cabang dispatch `generate_proposal` |
| `app/agent/prompts.py` (modify) | alur proposal + perluas anti-halusinasi |
| `static/index.html` (modify) | branding PT Maju Digital → PT Efisien Integrasi Indonesia |
| `tests/test_lead_repo.py` (modify) | unit `set_proposal` |
| `tests/test_tools.py` (modify) | test `generate_proposal` |
| `tests/test_orchestrator.py` (modify) | loop proposal |
| `tests/test_chat_api.py` (modify) | full-workflow acceptance |

**Tidak ada** model baru, migration baru, atau repository baru.

---

## Task 1: LeadRepository.set_proposal

**Files:**
- Modify: `app/repositories/lead_repo.py`
- Test: `tests/test_lead_repo.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lead_repo.py`:

```python
def test_set_proposal_stores_and_qualifies(session):
    user = _user(session, phone="0815")
    repo = LeadRepository(session)
    lead = repo.upsert(user.id, project_type="POS")
    proposal = {
        "scope": "POS 3 cabang",
        "timeline": "6-8 minggu",
        "cost": "Rp 25 juta",
        "deliverables": ["Aplikasi POS Android", "Dashboard web"],
    }
    repo.set_proposal(lead, proposal)
    assert lead.proposal == proposal
    assert lead.status == "qualified"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_lead_repo.py::test_set_proposal_stores_and_qualifies -v`
Expected: FAIL — `AttributeError: 'LeadRepository' object has no attribute 'set_proposal'`

- [ ] **Step 3: Add the method**

In `app/repositories/lead_repo.py`, add this method to `LeadRepository` (after `upsert`):

```python
    def set_proposal(self, lead: Lead, proposal: dict) -> Lead:
        lead.proposal = proposal
        lead.status = "qualified"
        self.session.flush()
        return lead
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_lead_repo.py::test_set_proposal_stores_and_qualifies -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/repositories/lead_repo.py tests/test_lead_repo.py
git commit -m "feat: LeadRepository.set_proposal (store proposal + mark qualified)"
```

---

## Task 2: generate_proposal tool

**Files:**
- Modify: `app/agent/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tools.py`:

```python
def test_dispatch_generate_proposal_stores_and_qualifies(session):
    user = _seed_user(session, phone="0850")
    LeadRepository(session).upsert(user.id, project_type="POS", requirements="3 cabang")
    out = json.loads(
        dispatch(
            ToolCall(
                name="generate_proposal",
                args={
                    "scope": "POS 3 cabang",
                    "timeline": "6-8 minggu",
                    "cost": "Rp 25 juta",
                    "deliverables": ["Aplikasi POS Android", "Dashboard web"],
                },
            ),
            session=session,
            user=user,
        )
    )
    assert out["status"] == "qualified"
    assert out["proposal"]["deliverables"] == ["Aplikasi POS Android", "Dashboard web"]
    lead = LeadRepository(session).get_latest(user.id)
    assert lead.proposal["scope"] == "POS 3 cabang"
    assert lead.status == "qualified"


def test_dispatch_generate_proposal_requires_lead(session):
    user = _seed_user(session, phone="0851")
    out = json.loads(
        dispatch(
            ToolCall(
                name="generate_proposal",
                args={"scope": "x", "timeline": "y", "cost": "z"},
            ),
            session=session,
            user=user,
        )
    )
    assert "Belum ada lead" in out["result"]
```

(`LeadRepository` sudah di-import di bagian atas `tests/test_tools.py`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py -k generate_proposal -v`
Expected: FAIL — unknown tool error → KeyError on `out["status"]`.

- [ ] **Step 3: Add the ToolSpec**

In `app/agent/tools.py`, add this `ToolSpec` to `TOOL_SPECS` (after the `notify_manager` spec):

```python
    ToolSpec(
        name="generate_proposal",
        description=(
            "Susun proposal awal (scope, timeline, biaya, deliverables) dari kebutuhan "
            "lead yang sudah digali. Panggil saat user meminta penawaran/proposal atau "
            "setelah kebutuhan cukup lengkap. Isi argumen secara realistis."
        ),
        parameters={
            "type": "object",
            "properties": {
                "scope": {"type": "string", "description": "Ringkasan lingkup pekerjaan"},
                "timeline": {"type": "string", "description": "Estimasi waktu, mis. '6-8 minggu'"},
                "cost": {"type": "string", "description": "Estimasi biaya, mis. 'Rp 25-30 juta'"},
                "deliverables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Daftar hasil yang diserahkan",
                },
            },
            "required": ["scope", "timeline", "cost"],
        },
    ),
```

- [ ] **Step 4: Add the dispatch branch**

In `app/agent/tools.py`, add this branch inside `dispatch` (after the `notify_manager` branch, before the final unknown-tool `return`):

```python
        if tool_call.name == "generate_proposal":
            lead = LeadRepository(session).get_latest(user.id)
            if lead is None:
                return json.dumps(
                    {"result": "Belum ada lead. Gali kebutuhan klien dulu sebelum membuat proposal."},
                    ensure_ascii=False,
                )
            proposal = {
                "scope": tool_call.args.get("scope", ""),
                "timeline": tool_call.args.get("timeline", ""),
                "cost": tool_call.args.get("cost", ""),
                "deliverables": tool_call.args.get("deliverables", []),
            }
            LeadRepository(session).set_proposal(lead, proposal)
            return json.dumps(
                {"lead_id": lead.id, "proposal": proposal, "status": lead.status},
                ensure_ascii=False,
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py -k generate_proposal -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add app/agent/tools.py tests/test_tools.py
git commit -m "feat: generate_proposal tool (structured proposal -> lead.proposal, qualify)"
```

---

## Task 3: System prompt — proposal flow

**Files:**
- Modify: `app/agent/prompts.py`

- [ ] **Step 1: Add the proposal flow paragraph**

In `app/agent/prompts.py`, insert the following **before** the final `PENTING:` paragraph:

```python
Setelah kebutuhan lead tergali (atau saat user meminta penawaran/proposal), panggil
`generate_proposal` dengan `scope`, `timeline`, `cost`, dan `deliverables` yang realistis
berdasarkan kebutuhan yang sudah dicatat (gunakan `get_lead` bila perlu mengingat detail).
Sampaikan ringkasan proposal kepada user, dan jelaskan bahwa ini estimasi awal.
```

- [ ] **Step 2: Extend the anti-hallucination rule**

In the final `PENTING:` paragraph, replace:

```python
sebelum tool terkait (`create_lead`/`create_meeting`/`create_ticket`/`assign_developer`)
benar-benar dipanggil dan
```

with:

```python
sebelum tool terkait
(`create_lead`/`create_meeting`/`create_ticket`/`assign_developer`/`generate_proposal`)
benar-benar dipanggil dan
```

- [ ] **Step 3: Verify the prompt imports cleanly**

Run: `uv run python -c "from app.agent.prompts import SYSTEM_PROMPT; print('generate_proposal' in SYSTEM_PROMPT)"`
Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add app/agent/prompts.py
git commit -m "feat: proposal flow in system prompt"
```

---

## Task 4: Orchestrator loop — proposal

**Files:**
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_orchestrator.py`:

```python
def test_proposal_loop_persists(session):
    from app.repositories.lead_repo import LeadRepository

    scripted = [
        LLMResponse(
            tool_calls=[
                ToolCall(name="create_lead", args={"project_type": "POS", "requirements": "3 cabang"})
            ]
        ),
        LLMResponse(
            tool_calls=[
                ToolCall(
                    name="generate_proposal",
                    args={
                        "scope": "POS 3 cabang",
                        "timeline": "6 minggu",
                        "cost": "Rp 25 juta",
                        "deliverables": ["Aplikasi POS"],
                    },
                )
            ]
        ),
        LLMResponse(text="Berikut proposal Anda."),
    ]
    llm = FakeLLM(responses=scripted)
    reply, user = handle_chat(
        session, llm, _FakeRetriever(), message="mau POS, buatkan proposal", phone="0877"
    )
    assert "proposal" in reply.lower()
    lead = LeadRepository(session).get_latest(user.id)
    assert lead.proposal["scope"] == "POS 3 cabang"
    assert lead.proposal["deliverables"] == ["Aplikasi POS"]
    assert lead.status == "qualified"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_orchestrator.py::test_proposal_loop_persists -v`
Expected: PASS. (Orchestrator already forwards `session`/`user` to `dispatch`; no orchestrator change needed.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_orchestrator.py
git commit -m "test: orchestrator loop for generate_proposal"
```

---

## Task 5: Polish — UI branding

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Fix the page title**

In `static/index.html`, replace:

```html
  <title>Efisien CS — PT Maju Digital</title>
```

with:

```html
  <title>Efisien CS — PT Efisien Integrasi Indonesia</title>
```

- [ ] **Step 2: Fix the heading**

In `static/index.html`, replace:

```html
  <h2>AI Customer Service — PT Maju Digital</h2>
```

with:

```html
  <h2>AI Customer Service — PT Efisien Integrasi Indonesia</h2>
```

- [ ] **Step 3: Verify no stale branding remains**

Run: `grep -n "Maju" static/index.html || echo "clean"`
Expected: `clean`

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "polish: fix UI branding to PT Efisien Integrasi Indonesia"
```

---

## Task 6: Full-workflow acceptance test

**Files:**
- Modify: `tests/test_chat_api.py`

- [ ] **Step 1: Write the acceptance test**

Append to `tests/test_chat_api.py`:

```python
def test_full_workflow_faq_lead_proposal_booking(build_client):
    from datetime import datetime

    from app.integrations.calendar import WIB, fmt_slot

    slot = datetime(2099, 1, 5, 9, 0, tzinfo=WIB)
    # One scripted FakeLLM drives the whole journey; it advances across POSTs.
    scripted = [
        # 1) FAQ
        LLMResponse(tool_calls=[ToolCall(name="search_knowledge_base", args={"query": "layanan"})]),
        LLMResponse(text="Layanan kami: ERP, AI, dan pengembangan aplikasi."),
        # 2) Lead
        LLMResponse(
            tool_calls=[
                ToolCall(name="create_lead", args={"project_type": "POS", "requirements": "3 cabang", "budget": "25 juta"})
            ]
        ),
        LLMResponse(text="Kebutuhan Anda sudah dicatat."),
        # 3) Proposal
        LLMResponse(
            tool_calls=[
                ToolCall(
                    name="generate_proposal",
                    args={"scope": "POS 3 cabang", "timeline": "6-8 minggu", "cost": "Rp 25 juta", "deliverables": ["Aplikasi POS"]},
                )
            ]
        ),
        LLMResponse(text="Berikut proposal Anda: scope POS 3 cabang, estimasi Rp 25 juta."),
        # 4) Booking
        LLMResponse(tool_calls=[ToolCall(name="get_available_slots", args={})]),
        LLMResponse(tool_calls=[ToolCall(name="create_meeting", args={"slot": fmt_slot(slot)})]),
        LLMResponse(text="Konsultasi Anda terjadwal."),
    ]
    client = build_client(
        FakeLLM(responses=scripted), _EmptyRetriever(), calendar=FakeCalendar([slot])
    )

    r1 = client.post("/chat", json={"message": "Apa layanan kalian?", "phone": "0890"})
    assert r1.status_code == 200
    assert "Layanan" in r1.json()["reply"]

    r2 = client.post("/chat", json={"message": "Mau bikin POS 3 cabang, budget 25 juta", "phone": "0890"})
    assert r2.status_code == 200
    assert "dicatat" in r2.json()["reply"]

    r3 = client.post("/chat", json={"message": "Tolong buatkan proposal", "phone": "0890"})
    assert r3.status_code == 200
    assert "proposal" in r3.json()["reply"].lower()

    r4 = client.post("/chat", json={"message": "Sekalian jadwalkan konsultasi", "phone": "0890"})
    assert r4.status_code == 200
    assert "terjadwal" in r4.json()["reply"]
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_chat_api.py::test_full_workflow_faq_lead_proposal_booking -v`
Expected: PASS. (`FakeCalendar` and `_EmptyRetriever` are already imported in `tests/test_chat_api.py`.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_chat_api.py
git commit -m "test: full-workflow acceptance (FAQ -> lead -> proposal -> booking)"
```

---

## Task 7: Full suite + final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `uv run pytest -q`
Expected: all tests pass (79 prior + 5 new Sprint 7 tests = ~84 total). No failures.

- [ ] **Step 2: Confirm tool registration**

Run: `uv run python -c "from app.agent.tools import TOOL_SPECS; print(len(TOOL_SPECS)); print('generate_proposal' in [t.name for t in TOOL_SPECS])"`
Expected: `13` and `True`.

- [ ] **Step 3: Confirm migration head unchanged (no new migration this sprint)**

Run: `uv run alembic current`
Expected: still `cb654acf820e` (Sprint 6 head) — Sprint 7 added no migration.

---

## Self-Review

**Spec coverage:**
- §2 No model/migration → confirmed (Task list has none) ✓
- §3 `LeadRepository.set_proposal` → Task 1 ✓
- §4 `generate_proposal` tool (structured args, inject user, no-lead message, store + qualify) → Task 2 ✓
- §5 System prompt (proposal flow + anti-hallucination) → Task 3 ✓
- §6 Polish: branding → Task 5; full-workflow acceptance → Task 6 ✓
- §7 Error handling → no-lead message (Task 2), deliverables default `[]` (Task 2) ✓
- §8 Testing (lead_repo/tool/orchestrator/full-workflow) → Tasks 1, 2, 4, 6 ✓
- §9 DOD → Task 7 verification ✓

**Type consistency:** `LeadRepository.set_proposal(lead, proposal)` used identically in Task 1 (repo), Task 2 (dispatch), and asserted in Tasks 1/2/4. Proposal dict keys `scope`/`timeline`/`cost`/`deliverables` consistent across tool, tests, and full-workflow. Tool name `generate_proposal` consistent across spec, dispatch, prompts, and tests.

**Placeholder scan:** none — every code/test/command step contains concrete content.
