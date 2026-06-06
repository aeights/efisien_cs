# Sprint 7 — Proposal Generation + Polish (final) — Design Spec

**Date:** 2026-06-06
**Status:** Approved (design phase)
**Feature:** 7 (generate proposal) + polish end-to-end & full workflow

## 1. Tujuan

Sprint penutup. Menambahkan kemampuan AI menyusun **proposal** (scope, timeline, biaya, deliverables) dari kebutuhan lead yang sudah digali, menyimpannya ke `lead.proposal`, dan menandai lead `qualified`. Plus polish: perbaikan branding UI dan satu **full-workflow acceptance test** yang menutup Definition of Done proyek.

Mengikuti arsitektur terkunci: lean (tanpa service layer), repository dipanggil langsung di `dispatch`, identitas user di-inject dari context, **LLM mengisi konten lewat skema tool (structured output), kode memvalidasi & menyimpan**, TDD dengan fake.

## 2. Model Data — tidak ada perubahan

Kolom `lead.proposal` (`Mapped[dict | None]`, JSON, nullable) **sudah ada sejak Sprint 3** (disiapkan untuk sprint ini). Sprint 7 hanya mengisinya. **Tidak ada model baru, tidak ada migration.**

Bentuk JSON yang disimpan di `lead.proposal`:
```json
{
  "scope": "Aplikasi POS untuk 3 cabang dengan sinkronisasi stok terpusat",
  "timeline": "6-8 minggu",
  "cost": "Rp 25-30 juta",
  "deliverables": ["Aplikasi POS Android", "Dashboard web admin", "Training 1 hari", "Garansi 3 bulan"]
}
```

## 3. Repository

### `LeadRepository.set_proposal(lead, proposal)` (baru)
- `lead.proposal = proposal`
- `lead.status = "qualified"` (menandai lead matang saat proposal dibuat)
- `self.session.flush()`, kembalikan `lead`.

Method lain (`get_latest`, `get_open`, `upsert`) tidak berubah.

## 4. Tool `generate_proposal` (`app/agent/tools.py`)

Ditambahkan ke `TOOL_SPECS` + satu cabang `dispatch` (signature tidak berubah — `session` & `user` cukup). Total tool menjadi **13**.

**Structured output via skema tool.** Argumen LLM:
- `scope` (string, wajib)
- `timeline` (string, wajib)
- `cost` (string, wajib)
- `deliverables` (array of string, opsional)

Perilaku dispatch:
- `LeadRepository(session).get_latest(user.id)` — identitas di-inject.
- Bila `lead is None` → `{"result": "Belum ada lead. Gali kebutuhan klien dulu sebelum membuat proposal."}` (pola sama `create_meeting`).
- Susun `proposal = {"scope", "timeline", "cost", "deliverables"}` (deliverables default `[]` bila tak diisi).
- `LeadRepository(session).set_proposal(lead, proposal)`.
- Kembalikan `{"lead_id": lead.id, "proposal": proposal, "status": lead.status}` (`status` = `qualified`).

## 5. System Prompt (`app/agent/prompts.py`)

- **Alur proposal:** setelah kebutuhan lead tergali (atau saat user meminta penawaran/proposal), panggil `generate_proposal` dengan `scope`/`timeline`/`cost`/`deliverables` yang realistis berdasarkan kebutuhan yang sudah dicatat (pakai `get_lead` bila perlu mengingat detail), lalu sampaikan ringkasan proposal kepada user. Proposal bersifat estimasi awal.
- **Anti-halusinasi (diperluas):** tambahkan `generate_proposal` ke daftar tool yang tak boleh diklaim sukses sebelum benar-benar dipanggil dan mengembalikan hasil.

## 6. Polish

### Branding UI (`static/index.html`)
Ganti "PT Maju Digital" → "PT Efisien Integrasi Indonesia" pada `<title>` dan `<h2>` (sisa placeholder Sprint 1).

### Full-workflow acceptance test (`tests/test_chat_api.py`)
Satu test e2e yang menjalankan perjalanan lengkap berurutan lewat `/chat` (satu `FakeLLM` ter-script yang dipakai lintas beberapa `POST`, karena FakeLLM melanjutkan skripnya antar panggilan):
1. **FAQ** — "Apa layanan kalian?" → `search_knowledge_base` → balasan layanan.
2. **Lead** — "Mau bikin POS 3 cabang, budget 25jt" → `create_lead` → balasan tercatat.
3. **Proposal** — "Tolong buatkan proposal" → `generate_proposal(...)` → balasan ringkasan proposal.
4. **Booking** — "Sekalian jadwalkan konsultasi" → `get_available_slots` → `create_meeting(slot)` → balasan terjadwal.

Assert tiap `POST` mengembalikan 200 + potongan teks balasan yang diharapkan. (Kebenaran data proposal di DB dijamin oleh test tool & orchestrator yang punya akses session langsung.) Test ini berfungsi sebagai **living acceptance check** Definition of Done.

## 7. Error Handling

- Cabang `generate_proposal` tetap dalam `try/except` global `dispatch` → `{"error": ...}`.
- Tanpa lead → pesan ramah, bukan exception.
- `deliverables` tak diisi → default `[]` (tidak crash).

## 8. Testing (TDD)

- **`tests/test_lead_repo.py` (tambahan):** `set_proposal` mengisi `lead.proposal` dan mengubah status ke `qualified`.
- **`tests/test_tools.py` (tambahan):**
  - `generate_proposal` meng-inject user, menyimpan proposal (termasuk `deliverables` list), mengembalikan status `qualified`.
  - `generate_proposal` tanpa lead → pesan "Belum ada lead".
- **`tests/test_orchestrator.py` (tambahan):** loop `generate_proposal` → `lead.proposal` tersimpan & status `qualified`.
- **`tests/test_chat_api.py` (tambahan):** full-workflow acceptance (4 langkah berurutan).

## 9. Definition of Done (proyek selesai)

Setelah Sprint 7, sistem memenuhi seluruh DOD master:
- ✅ Menjawab FAQ via RAG
- ✅ Kualifikasi & simpan lead
- ✅ **Generate proposal** (Sprint 7)
- ✅ Jadwalkan meeting
- ✅ Cek status proyek
- ✅ Buat & tugaskan tiket support
- ✅ Ingat percakapan (memori jangka panjang)
- ✅ Handoff ke manusia
- ✅ Semua aktivitas tersimpan di database
