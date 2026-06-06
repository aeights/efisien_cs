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
