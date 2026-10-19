# syntax=docker/dockerfile:1
# Build context: backend/. One process, non-root, embedding model baked in.
FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/backend
COPY pyproject.toml uv.lock ./
# Runtime dependencies only (no dev group), project itself not installed:
# the app runs from source so MODEL_CACHE_DIR resolves to /srv/backend/.cache.
RUN uv sync --frozen --no-dev --no-install-project
# Bake the fastembed model into the path app/services/embeddings.py reads.
RUN /srv/backend/.venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/srv/backend/.cache/fastembed')"
# huggingface_hub writes trees/*.json as 0600 root; the non-root runtime user
# must be able to read them (read-only: it never writes the cache).
RUN chmod -R a+rX,go-w /srv/backend/.cache

FROM python:3.12-slim-bookworm
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /srv/backend
COPY --from=build /srv/backend/.venv ./.venv
COPY --from=build /srv/backend/.cache ./.cache
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
ENV PATH=/srv/backend/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 EMBEDDING_THREADS=1
USER app
EXPOSE 8000
# Render sets PORT; 8000 locally. exec so uvicorn is PID 1 and gets SIGTERM.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
