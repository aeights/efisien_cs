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
