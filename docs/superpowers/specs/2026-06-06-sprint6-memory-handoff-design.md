# Sprint 6 — Memory + Human Handoff — Design Spec

**Date:** 2026-06-06
**Status:** Approved (design phase)
**Features:** 8 (human handoff) & 9 (long-term memory)

## 1. Tujuan

Dua kemampuan yang membuat AI terasa "ingat" dan tahu kapan menyerah ke manusia:

- **Feature 9 — Memori jangka panjang:** AI menyimpan fakta durable tentang user (nama, perusahaan, peran, preferensi) lewat tool `remember_fact`, dan memuatnya kembali tiap percakapan — termasuk di hari berikutnya — sehingga tidak menanyakan hal yang sama berulang.
- **Feature 8 — Human handoff:** saat AI sebaiknya tidak menangani sendiri (user minta manusia, negosiasi harga/kontrak, keluhan pembayaran, kegagalan/frustrasi berulang), AI memanggil `notify_sales`/`notify_manager` untuk mencatat eskalasi dan memberi tahu user bahwa tim akan menindaklanjuti.

Mengikuti arsitektur terkunci: lean (tanpa service layer), repository dipanggil langsung di `dispatch`, identitas user di-inject dari context, TDD dengan fake.

## 2. Model Data (2 tabel baru)

### `client_facts` (`app/models/client_fact.py`)
Memori jangka panjang, satu baris per fakta.

| kolom | tipe | catatan |
|---|---|---|
| `id` | Integer PK | |
| `user_id` | FK→`users.id`, indexed, NOT NULL | pemilik fakta |
| `key` | String(60) | mis. `nama`, `perusahaan`, `preferensi` |
| `value` | String(500) | nilainya |
| `created_at` | DateTime(timezone=True), server_default now() | |
| — | `UniqueConstraint(user_id, key)` | jaminan 1 nilai per key → mendukung upsert |

### `notifications` (`app/models/notification.py`)
Eskalasi/alert ke staf.

| kolom | tipe | catatan |
|---|---|---|
| `id` | Integer PK | |
| `target_role` | String(16) | `sales`/`manager`/`developer` |
| `reason` | String(255) | alasan eskalasi (diisi agent) |
| `payload` | JSON, nullable | identitas user (nama/phone/email) — diisi otomatis oleh kode |
| `status` | String(16), default `sent`, server_default `sent` | `pending`/`sent`; kini langsung `sent` karena console = kanal aktif |
| `created_at` | DateTime(timezone=True), server_default now() | |

**Relasi:** `user 1─* client_fact`. `notifications` berdiri sendiri (tak ber-FK; `payload` menyimpan identitas).

## 3. Repository

### `ClientFactRepository` (`app/repositories/client_fact_repo.py`)
- `upsert(user_id, key, value) -> ClientFact` — cari baris `(user_id, key)`; bila ada → perbarui `value`; bila tidak → buat baru. `flush()`. (Pola sama upsert lead Sprint 3.)
- `list_for_user(user_id) -> list[ClientFact]` — semua fakta user, urut `id`.

### `NotificationRepository` (`app/repositories/notification_repo.py`)
- `create(target_role, *, reason, payload=None) -> Notification` — status `sent`, `flush()`.

## 4. Tools (`app/agent/tools.py`)

Tiga tool baru ditambahkan ke `TOOL_SPECS` + cabang `dispatch` (signature `dispatch` tidak berubah — `session` & `user` sudah tersedia). Total tool menjadi **12**.

### `remember_fact`
Argumen LLM: `key` (wajib), `value` (wajib).
- `user_id` di-inject dari `user.id`.
- `ClientFactRepository.upsert(user.id, key, value)`.
- Kembalikan `{"key", "value", "result": "Fakta disimpan."}`.

### `notify_sales` / `notify_manager`
Argumen LLM: `reason` (wajib).
- `payload` dibangun otomatis dari identitas user: `{"name", "phone", "email"}` — bukan dari LLM.
- `NotificationRepository.create(target_role, reason=reason, payload=payload)` dengan `target_role` `"sales"` / `"manager"`.
- Console log via `print` (notifikasi internal sederhana; integrasi email/WA/Slack ditunda).
- Kembalikan `{"notification_id", "target_role", "status", "result"}`.
- Implementasi berbagi helper internal `_notify(session, user, role, reason)` agar dua tool tidak menduplikasi logika.

## 5. Orchestrator (`app/agent/orchestrator.py`)

Satu perubahan: **memuat memori ke system prompt** tiap panggilan.

- Sebelum loop tool-calling: `facts = ClientFactRepository(session).list_for_user(user.id)`.
- Bangun blok teks via helper, mis.:
  ```
  \n\nYang sudah Anda ketahui tentang pengguna ini (dari percakapan sebelumnya):
  - nama: Budi
  - perusahaan: Toko Maju
  ```
- `system = SYSTEM_PROMPT + blok` bila ada fakta; `SYSTEM_PROMPT` apa adanya bila kosong.
- `system` yang sudah diperkaya inilah yang dikirim ke `llm.generate(system, convo, tools=TOOL_SPECS)` di dalam loop.
- Fakta dimuat **sekali** di awal (sebelum loop), bukan tiap iterasi.

## 6. System Prompt (`app/agent/prompts.py`)

Tambahkan dua paragraf:
- **Memori:** saat user menyebut fakta durable tentang dirinya (nama, perusahaan, peran, preferensi), panggil `remember_fact(key, value)` untuk menyimpannya. Manfaatkan fakta yang sudah diketahui (lihat blok memori di awal) secara natural — jangan menanyakan ulang yang sudah diingat.
- **Handoff:** bila user meminta berbicara dengan manusia, atau topik di luar kapasitas Anda (negosiasi harga/kontrak, keluhan pembayaran/tagihan), atau terjadi kegagalan/frustrasi berulang, panggil `notify_sales` (urusan penjualan/komersial) atau `notify_manager` (eskalasi/komplain) dengan `reason` yang jelas, lalu sampaikan kepada user bahwa tim kami akan menindaklanjuti. Jangan menyatakan tim sudah dihubungi sebelum tool benar-benar dipanggil.

## 7. Error Handling

- Tiap cabang tool tetap dalam `try/except` global `dispatch` → `{"error": ...}` ke model.
- `remember_fact` tanpa `key`/`value` → tetap aman (string kosong tersimpan; prompt memandu agar diisi).
- Tabel/koneksi bermasalah → exception tertangkap, chat tidak crash.

## 8. Testing (TDD)

- **`tests/test_client_fact_repo.py`:** `upsert` buat-baru; `upsert` memperbarui key yang sama (tak menambah baris); `list_for_user`.
- **`tests/test_notification_repo.py`:** `create` → status `sent`, payload tersimpan.
- **`tests/test_tools.py` (tambahan):**
  - `remember_fact` meng-inject `user_id` & upsert (panggil dua kali key sama → 1 baris, value terbaru).
  - `notify_sales` & `notify_manager` menulis baris dengan `target_role` benar & `payload` dari identitas user.
- **`tests/test_orchestrator.py` (tambahan):**
  - Fakta user **muncul di system prompt** yang dikirim ke LLM (assert lewat `llm.calls[0][0]`).
  - Loop `remember_fact` → fakta tersimpan.
  - Loop handoff (`notify_manager`) → baris notification tersimpan.
- **`tests/test_chat_api.py` (tambahan):** e2e `/chat` alur handoff (LLM di-stub) — wiring 200 + reply.
- `tests/conftest.py`, `test_chat_api.py`, `alembic/env.py` meng-import `ClientFact`, `Notification` (`# noqa: F401`).

## 9. Definition of Done (Sprint 6)

- AI menyimpan fakta durable lewat `remember_fact` dan **memuatnya kembali** ke konteks tiap percakapan (termasuk hari berikutnya, karena fakta terikat ke `User`).
- AI dapat melakukan handoff: menulis baris `notification` untuk sales/manager + console log, lalu memberi tahu user.
- Seluruh alur tertutup test (unit, tool, orchestrator, e2e) dan suite lama tetap hijau.
- Migration `client_facts` + `notifications` diterapkan bersih.
