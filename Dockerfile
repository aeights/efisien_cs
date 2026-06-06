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
