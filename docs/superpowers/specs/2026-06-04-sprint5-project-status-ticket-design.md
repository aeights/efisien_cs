# Sprint 5 — Project Status + Support Ticket — Design Spec

**Date:** 2026-06-04
**Status:** Approved (design phase)
**Features:** 5 (cek status proyek) & 6 (buat & tugaskan tiket support)

## 1. Tujuan

Memungkinkan AI Customer Service melayani **klien existing**:

- **Feature 5 — Cek status proyek:** klien menanyakan progres proyeknya; AI memanggil `get_project_status` dan menjawab dengan data nyata (nama, jenis, progres, status, detail).
- **Feature 6 — Tiket support:** klien melaporkan masalah/permintaan; AI menggali deskripsi, mengklasifikasi kategori & prioritas, memanggil `create_ticket`, lalu `assign_developer` untuk menandai tiket siap dikerjakan.

Mengikuti arsitektur yang sudah terkunci: lean (tanpa service layer), repository dipanggil langsung di `dispatch`, identitas user di-inject dari context (bukan dari argumen LLM), TDD dengan fake.

## 2. Model Data (2 tabel baru)

### `projects` (`app/models/project.py`)
Proyek milik klien existing. **Tidak dibuat oleh agent** — diisi lewat seed script (staf yang membuat proyek di dunia nyata).

| kolom | tipe | catatan |
|---|---|---|
| `id` | Integer PK | |
| `client_id` | FK→`users.id`, indexed, NOT NULL | pemilik proyek |
| `name` | String(120) | mis. "Aplikasi POS Toko A" |
| `type` | String(120) | mis. POS, Website, Mobile App |
| `progress` | Integer, default 0, server_default "0" | 0–100 |
| `status` | String(16), default `in_progress`, server_default `in_progress` | `planning`/`in_progress`/`completed`/`on_hold` |
| `details` | JSON, nullable | mis. `{"backend":"done","frontend":80}` |
| `created_at` | DateTime(timezone=True), server_default now() | |

### `tickets` (`app/models/ticket.py`)
| kolom | tipe | catatan |
|---|---|---|
| `id` | Integer PK | |
| `user_id` | FK→`users.id`, indexed, **NOT NULL** | pemilik tiket — di-inject dari context |
| `project_id` | FK→`projects.id`, indexed, **nullable** | auto-tautkan proyek terbaru user kalau ada, else NULL |
| `category` | String(16) | `bug`/`feature`/`question` — diisi agent |
| `priority` | String(8) | `low`/`med`/`high` — diisi agent |
| `status` | String(16), default `open`, server_default `open` | `open`/`assigned`/`closed` |
| `description` | String(500) | isi keluhan/permintaan |
| `assigned_developer` | String(120), nullable | diisi saat `assign_developer` |
| `created_at` | DateTime(timezone=True), server_default now() | |

**Relasi:** `user 1─* project`, `user 1─* ticket`, `project 1─* ticket` (project_id boleh NULL).

## 3. Repository

### `ProjectRepository` (`app/repositories/project_repo.py`)
- `create(client_id, *, name, type, progress=0, status="in_progress", details=None) -> Project` — flush, return.
- `list_for_user(user_id) -> list[Project]` — semua proyek user, urut `id`.

### `TicketRepository` (`app/repositories/ticket_repo.py`)
- `create(user_id, *, description, category, priority, project_id=None) -> Ticket` — status `open`, flush, return.
- `get_latest_for_user(user_id) -> Ticket | None` — tiket terbaru user (order by `id` desc).
- `assign(ticket, *, developer="Tim Development") -> Ticket` — set `status="assigned"`, `assigned_developer=developer`, flush.

## 4. Tools (`app/agent/tools.py`)

Tiga tool baru ditambahkan ke `TOOL_SPECS` dan cabang baru di `dispatch` (signature `dispatch` tidak berubah — `session` & `user` sudah tersedia).

### `get_project_status` (tanpa argumen)
Ambil semua proyek user saat ini via `ProjectRepository.list_for_user`. Kembalikan:
```json
{"projects": [{"name": "...", "type": "...", "progress": 80, "status": "in_progress", "details": {...}}]}
```
Kalau kosong → `{"result": "Belum ada proyek terdaftar atas nama Anda."}`

### `create_ticket`
Argumen LLM: `description` (wajib), `category` (`bug`/`feature`/`question`), `priority` (`low`/`med`/`high`).
- `user_id` di-inject dari `user.id` (bukan dari LLM).
- `category`/`priority` divalidasi terhadap set yang sah; bila tidak valid → fallback `category="question"`, `priority="med"`.
- `project_id` = proyek terbaru user (`list_for_user`[-1]) bila ada, else `None`.
- Kembalikan `{"ticket_id", "category", "priority", "status", "project_id"}`.

### `assign_developer` (tanpa argumen)
- Target tiket **terbaru** milik user via `get_latest_for_user` (pola sama seperti `send_invitation`).
- Bila belum ada tiket → `{"result": "Belum ada tiket untuk ditugaskan."}`.
- `TicketRepository.assign(ticket)` → status `assigned`, `assigned_developer="Tim Development"`.
- Console log (mis. `print`) sebagai notifikasi internal sederhana — tabel `notification` **ditunda ke Sprint 6** sesuai rencana.
- Kembalikan `{"ticket_id", "status", "assigned_developer"}`.

## 5. System Prompt (`app/agent/prompts.py`)

Tambahkan dua alur:
- **Cek status:** klien existing menanyakan progres → panggil `get_project_status` → ringkas hasilnya.
- **Tiket support:** klien melapor masalah/permintaan → gali deskripsi singkat → tentukan `category` & `priority` dari isi keluhan → `create_ticket` → `assign_developer` → beri tahu user tiket sudah dibuat & ditugaskan, sebutkan nomor tiket.

Perkuat aturan anti-halusinasi yang sudah ada: jangan klaim tiket sudah dibuat/ditugaskan atau status proyek tertentu sebelum tool terkait benar-benar dipanggil dan mengembalikan hasil sukses.

## 6. Migration & Seed

- **Migration Alembic:** satu revisi menambah tabel `projects` + `tickets`, `down_revision = "2e298145de06"` (meetings). Hanya `create_table` — tidak ada drop. Model di-import di `migrations/env.py`/`conftest` agar tabel terdaftar.
- **`scripts/seed_projects.py`:** repeatable — buat (atau cari) satu user demo + 1–2 proyek dengan progres/status berbeda, agar `get_project_status` bisa di-smoke-test dengan data nyata. Idempoten (cek dulu sebelum insert).

## 7. Error Handling

- Tiap cabang tool tetap dalam `try/except` global `dispatch` → mengembalikan `{"error": ...}` ke model.
- Enum `category`/`priority` tidak valid → fallback diam-diam ke default yang sah (tidak meng-crash).
- `assign_developer`/`create_ticket` tanpa data prasyarat → pesan ramah, bukan exception.

## 8. Testing (TDD)

- **`tests/test_project_repo.py`:** `create` + `list_for_user`.
- **`tests/test_ticket_repo.py`:** `create` (status open, project_id nullable), `get_latest_for_user`, `assign` (status→assigned, developer terisi).
- **`tests/test_tools.py` (tambahan):**
  - `get_project_status` kosong & berisi.
  - `create_ticket` meng-inject `user_id`, auto-tautkan `project_id`, fallback enum tidak valid.
  - `assign_developer` mengubah status & mengisi developer; pesan saat belum ada tiket.
- **`tests/test_orchestrator.py` (tambahan):** loop alur tiket `create_ticket` → `assign_developer` → reply, tiket tersimpan & ter-assign.
- **`tests/test_chat_api.py` (tambahan):** e2e `/chat` alur tiket + alur cek status proyek (LLM di-stub).
- `tests/conftest.py` & `test_chat_api.py` meng-import model `Project`, `Ticket` (`# noqa: F401`) agar tabel dibuat.

## 9. Definition of Done (Sprint 5)

- AI dapat menjawab status proyek klien existing dari data DB (`get_project_status`).
- AI dapat membuat tiket support dengan kategori & prioritas, tertaut ke user (dan proyek bila ada).
- AI dapat menugaskan tiket (status `open → assigned`) dengan notifikasi console.
- Seluruh alur tertutup test (unit, tool, orchestrator, e2e) dan suite lama tetap hijau.
