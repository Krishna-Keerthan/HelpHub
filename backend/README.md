# HelpHub backend

FastAPI service for HelpHub: tenant-scoped auth, document upload and chunking, hybrid search (pgvector and tsvector) and streamed, cited chat answers. It uses async SQLAlchemy 2, Alembic migrations and PostgreSQL with Row-Level Security.

Layering is `app/api` -> `app/services` -> `app/db`: routes hold no business logic and SQL lives only under `app/db`. The rules and their enforcement are described in the root [CLAUDE.md](../CLAUDE.md) and checked by [scripts/gate.sh](../scripts/gate.sh).

## Setup

See the root [README](../README.md) for prerequisites, the `.env` variable names, starting Postgres and creating the first workspace.

## Run and test

From this directory:

```bash
uv sync
uv run alembic upgrade head
uv run fastapi dev app/main.py                # API on :8000, docs at /docs
uv run pytest                                 # default run; slow tests are skipped
uv run pytest -m "slow or not slow"           # everything
uv run ruff check . && uv run ruff format .
```

Test layout: [tests/README.md](tests/README.md). Run one pytest session at a time; they share a database.

## More

- [Chat stream contract](../docs/api/chat-stream.md) (`POST /chat/stream`, SSE events and error codes)
- [Accepted risks](../docs/review/accepted-risks.md)
- [Deployment runbook](../docs/deploy/runbook.md)
