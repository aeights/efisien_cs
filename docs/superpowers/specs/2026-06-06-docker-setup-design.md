# Docker Setup (Compose) — Design Spec

**Date:** 2026-06-06
**Status:** Approved (design phase)
**Goal:** Menjalankan proyek (app FastAPI + PostgreSQL) dengan satu perintah `docker compose up`, tanpa mengubah kode aplikasi.

## 1. Tujuan & Batasan

- **Satu perintah:** `docker compose up --build` → DB nyala, migration jalan, index RAG dibangun (sekali), server siap di `http://localhost:8000`.
- **Tidak mengubah kode aplikasi** — hanya menambah file infrastruktur. Konfigurasi sudah membaca env var (`DATABASE_URL`, `GEMINI_API_KEY`, dll.) lewat `pydantic-settings`, jadi cukup di-pass dari Compose.
- **Chroma tetap embedded** (PersistentClient di `data/chroma`) — tidak ada service Chroma terpisah; index persist lewat named volume.
- **Non-root** di container app (keamanan dasar).
- **Rahasia tidak di-bake** ke image; `.env` dibaca runtime oleh Compose.

## 2. File yang Dibuat

| File | Tanggung jawab |
|---|---|
| `Dockerfile` | Build image aplikasi (uv + Python 3.14, deps dari `uv.lock`, source app, user non-root). |
| `docker-entrypoint.sh` | Startup: migration → ingest-bila-kosong → jalankan uvicorn. |
| `docker-compose.yml` | Orkestrasi service `db` (Postgres 17) + `app`, volume, env, healthcheck. |
| `.dockerignore` | Kecualikan file yang tak perlu/rahasia dari build context. |

Tidak ada perubahan pada kode `app/`, `tests/`, atau migrasi.

## 3. Dockerfile

- **Base image:** `ghcr.io/astral-sh/uv:python3.14-bookworm-slim` (uv + Python 3.14 sesuai dev).
- **Workdir:** `/app`.
- **Layer dependency (cache-friendly):** copy `pyproject.toml` + `uv.lock` dulu → `uv sync --frozen --no-dev --no-install-project` (install dependency saja, tanpa dev/test).
- **Layer source:** copy `app/`, `alembic/`, `alembic.ini`, `static/`, `data/docs/`, `scripts/`, `docker-entrypoint.sh` → `uv sync --frozen --no-dev` (install project).
- **Non-root user:** buat user `appuser` (uid 1000). `mkdir -p /app/data/chroma` lalu `chown -R appuser:appuser /app` **sebelum** volume di-mount pertama kali, supaya named volume `chroma_index` mewarisi kepemilikan `appuser` saat diinisialisasi (sehingga ingest bisa menulis index). `USER appuser`.
- `EXPOSE 8000`.
- `ENTRYPOINT ["/app/docker-entrypoint.sh"]`.

## 4. docker-entrypoint.sh

Skrip bash (`set -e`):
1. `uv run alembic upgrade head` — buat/migrasi 8 tabel (idempoten; DB sudah dijamin siap oleh `depends_on: service_healthy`).
2. **Ingest bila perlu:** jika `data/chroma` kosong **dan** `GEMINI_API_KEY` tidak kosong → `uv run python scripts/ingest_docs.py`. Bila key kosong → cetak peringatan dan lewati (app tetap jalan; FAQ kosong sampai index dibangun). Bila index sudah ada → lewati (hemat kuota).
3. `exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`.

## 5. docker-compose.yml

**Service `db`:**
- `image: postgres:17`
- `environment:` `POSTGRES_USER=efisien`, `POSTGRES_PASSWORD=efisien`, `POSTGRES_DB=efisien_cs`
- `healthcheck:` `pg_isready -U efisien -d efisien_cs` (interval 5s, retries 5)
- `volumes:` `pgdata:/var/lib/postgresql/data`

**Service `app`:**
- `build: .`
- `depends_on:` `db: { condition: service_healthy }`
- `env_file: .env` — mengambil `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL`.
- `environment:` `DATABASE_URL=postgresql+psycopg://efisien:efisien@db:5432/efisien_cs` — **override** nilai `.env` lokal (yang menunjuk `localhost`); `environment` menang atas `env_file` di Docker Compose.
- `ports:` `"8000:8000"`
- `volumes:` `chroma_index:/app/data/chroma` (index RAG persist antar restart).

**Volumes:** `pgdata`, `chroma_index`.

## 6. .dockerignore

Kecualikan: `.git`, `.venv`, `__pycache__/`, `*.pyc`, `.pytest_cache`, `.env`, `data/chroma`, `docs/`, `*.md` di root (opsional), `.python-version` boleh ikut. Tujuan: build context ramping + rahasia (`.env`) & index lokal tidak ikut.

## 7. Alur Data / Cara Pakai

```
docker compose up --build
  db  → inisialisasi, healthy
  app → alembic upgrade head (8 tabel)
       → ingest sekali (jika index kosong & ada GEMINI_API_KEY)
       → uvicorn :8000
  → http://localhost:8000  (UI chat)
```

Perintah pendukung (didokumentasikan):
- Build saja: `docker compose build`
- Ingest manual (mis. setelah update dokumen): `docker compose run --rm app uv run python scripts/ingest_docs.py`
- Seed proyek demo: `docker compose run --rm app uv run python scripts/seed_projects.py`
- Hentikan + hapus volume (reset): `docker compose down -v`

## 8. Error Handling / Edge Cases

- **DB belum siap:** dicegah oleh `depends_on: service_healthy` + healthcheck `pg_isready`.
- **`GEMINI_API_KEY` kosong:** app tetap boot; ingest dilewati dengan peringatan; chat live akan gagal saat dipanggil (sesuai perilaku tanpa key).
- **Volume Chroma owned root:** dicegah dengan `chown appuser` pada `/app/data/chroma` di image sebelum volume diinisialisasi.
- **`.env` lokal `DATABASE_URL=localhost`:** di-override oleh `environment` di service `app`.

## 9. Verifikasi (Definition of Done)

- `docker compose config` valid (tanpa error).
- `docker compose build` sukses.
- (Manual, butuh Docker daemon) `docker compose up` → `curl http://localhost:8000/health` mengembalikan `{"status":"ok"}`; UI chat tampil di `/`.
- Suite test lokal tetap hijau (file infra tidak menyentuh kode).
