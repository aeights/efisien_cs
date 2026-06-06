# Docker Setup (Compose) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menjalankan proyek (FastAPI app + PostgreSQL) dengan satu perintah `docker compose up --build`, tanpa mengubah kode aplikasi.

**Architecture:** Image app berbasis `uv` + Python 3.14, dijalankan sebagai user non-root. Entrypoint menjalankan migrasi Alembic lalu ingest RAG (hanya bila index kosong) sebelum start uvicorn. Compose mengorkestrasi service `app` + `db` (Postgres 17) dengan healthcheck, named volume untuk data Postgres & index Chroma. Rahasia (`.env`) dibaca runtime, tidak di-bake ke image.

**Tech Stack:** Docker, Docker Compose, Postgres 17, `ghcr.io/astral-sh/uv:python3.14-bookworm-slim`, FastAPI/uvicorn.

---

## File Structure

| File | Tanggung jawab |
|---|---|
| `.dockerignore` (create) | Kecualikan file tak perlu/rahasia dari build context |
| `docker-entrypoint.sh` (create) | Startup: migrasi → ingest-bila-kosong → uvicorn |
| `Dockerfile` (create) | Build image app (uv + Python 3.14, non-root) |
| `docker-compose.yml` (create) | Orkestrasi `app` + `db`, volume, env, healthcheck |
| `docs/menjalankan-dengan-docker.md` (create) | Instruksi pakai (Bahasa) |

**Tidak ada perubahan** pada `app/`, `tests/`, `pyproject.toml`, atau migrasi.

**Catatan verifikasi:** sebagian langkah memakai `docker`/`docker compose`. Jika Docker daemon tidak tersedia di mesin saat eksekusi, langkah verifikasi yang butuh daemon dilewati dengan catatan — file tetap dibuat dan di-commit (akan dijalankan user di mesin ber-Docker).

---

## Task 1: .dockerignore

**Files:**
- Create: `.dockerignore`

- [ ] **Step 1: Create the file**

Create `.dockerignore`:

```
.git
.gitignore
.venv
__pycache__/
*.pyc
*.pyo
.pytest_cache
.env
data/chroma
docs/
tests/
.python-version
```

- [ ] **Step 2: Verify key exclusions present**

Run: `grep -E '^(\.env|data/chroma|\.venv)$' .dockerignore`
Expected: tiga baris (`.env`, `data/chroma`, `.venv`) tercetak — memastikan rahasia & index lokal tak masuk image.

- [ ] **Step 3: Commit**

```bash
git add .dockerignore
git commit -m "chore: .dockerignore for app image build context"
```

---

## Task 2: docker-entrypoint.sh

**Files:**
- Create: `docker-entrypoint.sh`

- [ ] **Step 1: Create the script**

Create `docker-entrypoint.sh`:

```sh
#!/bin/sh
set -e

echo "[entrypoint] Menjalankan migrasi database (alembic upgrade head)..."
uv run alembic upgrade head

if [ -z "$(ls -A /app/data/chroma 2>/dev/null)" ]; then
  if [ -n "$GEMINI_API_KEY" ]; then
    echo "[entrypoint] Index RAG kosong -> membangun (ingest)..."
    uv run python scripts/ingest_docs.py
  else
    echo "[entrypoint] PERINGATAN: GEMINI_API_KEY kosong; lewati ingest. FAQ kosong sampai index dibangun."
  fi
else
  echo "[entrypoint] Index RAG sudah ada; lewati ingest."
fi

echo "[entrypoint] Menjalankan server di :8000..."
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: Verify shell syntax**

Run: `sh -n docker-entrypoint.sh && echo "syntax OK"`
Expected: `syntax OK` (tanpa error parsing).

- [ ] **Step 3: Commit**

```bash
git add docker-entrypoint.sh
git commit -m "feat: docker entrypoint (migrate, ingest-if-empty, run uvicorn)"
```

---

## Task 3: Dockerfile

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Create the Dockerfile**

Create `Dockerfile`:

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

# 1) Dependency layer (cache-friendly): install deps only, not the project.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Application source.
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY static/ ./static/
COPY data/docs/ ./data/docs/
COPY scripts/ ./scripts/
COPY docker-entrypoint.sh ./

# 3) Finalize environment for the project.
RUN uv sync --frozen --no-dev

# 4) Non-root user. Pre-create + own the chroma dir so the named volume
#    mounted there inherits writable ownership on first init.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data/chroma \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
```

- [ ] **Step 2: Verify the source dirs referenced by COPY exist**

Run: `ls -d app alembic alembic.ini static data/docs scripts pyproject.toml uv.lock`
Expected: semua path tercetak tanpa error (semua sumber yang di-`COPY` memang ada).

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat: Dockerfile (uv + python 3.14, non-root app image)"
```

---

## Task 4: docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create the compose file**

Create `docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_USER: efisien
      POSTGRES_PASSWORD: efisien
      POSTGRES_DB: efisien_cs
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U efisien -d efisien_cs"]
      interval: 5s
      timeout: 5s
      retries: 5
    volumes:
      - pgdata:/var/lib/postgresql/data

  app:
    build: .
    depends_on:
      db:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+psycopg://efisien:efisien@db:5432/efisien_cs
    ports:
      - "8000:8000"
    volumes:
      - chroma_index:/app/data/chroma

volumes:
  pgdata:
  chroma_index:
```

- [ ] **Step 2: Validate the compose file**

Run: `docker compose config >/dev/null && echo "compose OK"`
Expected: `compose OK`. (Memvalidasi sintaks + resolusi env. Butuh `.env` ada di root — sudah ada. Jika `docker` tidak terpasang, lewati langkah ini dengan catatan dan lanjut.)

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: docker-compose (app + postgres 17, healthcheck, volumes)"
```

---

## Task 5: Dokumentasi cara pakai

**Files:**
- Create: `docs/menjalankan-dengan-docker.md`

- [ ] **Step 1: Create the doc**

Create `docs/menjalankan-dengan-docker.md`:

```markdown
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
```

- [ ] **Step 2: Verify the doc is not gitignored**

Run: `git check-ignore docs/menjalankan-dengan-docker.md || echo "tracked"`
Expected: `tracked` (hanya `docs/penjelasan-kode.md` yang gitignored; doc ini ikut ke git).

- [ ] **Step 3: Commit**

```bash
git add docs/menjalankan-dengan-docker.md
git commit -m "docs: how to run with Docker (Bahasa)"
```

---

## Task 6: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Confirm all Docker artifacts present**

Run: `ls Dockerfile docker-compose.yml docker-entrypoint.sh .dockerignore docs/menjalankan-dengan-docker.md`
Expected: kelima file tercetak.

- [ ] **Step 2: Validate compose once more (if Docker available)**

Run: `docker compose config >/dev/null && echo "compose OK"`
Expected: `compose OK`. (Jika Docker tidak tersedia, catat bahwa validasi dilewati; file sudah ditinjau manual.)

- [ ] **Step 3: (Optional, butuh Docker daemon) Build image**

Run: `docker compose build`
Expected: build sukses (image `app` ter-build). Langkah ini berat & opsional; boleh dilakukan user di mesin ber-Docker. Jalankan penuh dengan `docker compose up` lalu `curl http://localhost:8000/health` → `{"status":"ok"}`.

- [ ] **Step 4: Confirm local test suite still green (no app code touched)**

Run: `uv run pytest -q`
Expected: 84 passed (file infra tidak menyentuh kode aplikasi).

---

## Self-Review

**Spec coverage:**
- §2 File list (Dockerfile, entrypoint, compose, dockerignore) → Tasks 1–4; doc → Task 5 ✓
- §3 Dockerfile (uv base, cache layer, source copy, non-root, chroma chown, expose, entrypoint) → Task 3 ✓
- §4 Entrypoint (migrate, ingest-if-empty + key guard, exec uvicorn) → Task 2 ✓
- §5 Compose (db env/healthcheck/volume, app build/depends_on/env_file/DATABASE_URL override/ports/volume, volumes) → Task 4 ✓
- §6 .dockerignore → Task 1 ✓
- §7 Cara pakai (perintah pendukung) → Task 5 doc ✓
- §8 Edge cases (DB ready via healthcheck, key kosong → skip ingest, chroma chown, DATABASE_URL override) → covered in Tasks 2/3/4 ✓
- §9 Verifikasi (compose config, build, test hijau) → Task 6 ✓

**Type/consistency:** Nama service `db`/`app`, user/pass `efisien`/`efisien`, DB `efisien_cs`, `DATABASE_URL=postgresql+psycopg://efisien:efisien@db:5432/efisien_cs`, port `8000`, mount `/app/data/chroma`, user `appuser` (uid 1000) — konsisten antara Dockerfile, entrypoint, compose, dan doc.

**Placeholder scan:** none — setiap langkah berisi konten file/perintah konkret.
