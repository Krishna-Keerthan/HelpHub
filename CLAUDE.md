# HelpHub
Multi-tenant support knowledge engine. Backend in backend/ (FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL + pgvector). Later: Elasticsearch, Redis/SAQ, LangGraph, Groq, Next.js.

## Commands (run from backend/)
- API: uv run fastapi dev app/main.py
- Tests: uv run pytest
- Lint: uv run ruff check . && uv run ruff format .
- Migrate: uv run alembic upgrade head
- Services: docker compose up -d (repo root)

## Rules
- Every tenant-owned table has tenant_id. Tenant comes from the verified JWT only.
- Runtime uses DATABASE_URL (limited role). Only Alembic uses MIGRATION_DATABASE_URL (owner).
- All DB and network calls are async. Type hints everywhere.
- Small changes only; write or update a test for each new behavior.
- Never read or edit .env.