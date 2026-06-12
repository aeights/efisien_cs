# Menjalankan dengan Docker

## Prasyarat
- Docker + Docker Compose terpasang.
- File `.env` di root (salin dari `.env.example`, isi `GEMINI_API_KEY`).
  `DATABASE_URL` di `.env` boleh menunjuk localhost — Compose menimpanya
  agar app menunjuk service `db`.

## Jalankan (satu perintah)
```bash
docker compose up --build
```
Yang terjadi otomatis: service `db` (Postgres 17) nyala dan sehat → container
`app` menjalankan migrasi (`alembic upgrade head`) → membangun index RAG sekali
(jika kosong & ada `GEMINI_API_KEY`) → menjalankan server.

Buka **http://localhost:8000** untuk UI chat. Cek kesehatan: `curl http://localhost:8000/health`.

## Perintah pendukung
- Build saja: `docker compose build`
- Ingest ulang index (setelah dokumen berubah): `docker compose run --rm app uv run python scripts/ingest_docs.py`
- Seed proyek demo: `docker compose run --rm app uv run python scripts/seed_projects.py`
- Hentikan: `docker compose down`
- Reset total (hapus data DB + index): `docker compose down -v`

## Catatan
- Rahasia (`.env`) tidak ikut ke dalam image; dibaca runtime oleh Compose.
- Index Chroma & data Postgres persist di named volume (`chroma_index`, `pgdata`).
- Container app berjalan sebagai user non-root (`appuser`).

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
