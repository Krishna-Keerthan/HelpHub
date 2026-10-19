# syntax=docker/dockerfile:1
# Build context: backend/. One process, non-root. Embeddings are hosted
# (Cloudflare), so there is no local model and no fastembed/onnxruntime here.
FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/backend
COPY pyproject.toml uv.lock ./
# Runtime dependencies only (no dev group, so no local-embeddings), project
# itself not installed: the app runs from source.
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim-bookworm
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /srv/backend
COPY --from=build /srv/backend/.venv ./.venv
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
ENV PATH=/srv/backend/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    EMBEDDING_PROVIDER=cloudflare
USER app
EXPOSE 8000
# Render sets PORT; 8000 locally. exec so uvicorn is PID 1 and gets SIGTERM.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
