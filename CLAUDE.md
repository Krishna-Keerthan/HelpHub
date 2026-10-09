# HelpHub
Multi-tenant support knowledge engine. Backend in backend/ (FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL + pgvector). Later: Elasticsearch, Redis/SAQ, LangGraph, Groq, Next.js.

## Platform
Project lives in WSL2 Ubuntu at ~/projects/helphub. Use bash and Linux paths only. Never use PowerShell or Windows paths.

## Commands (run from backend/)
- API: uv run fastapi dev app/main.py
- Tests: uv run pytest
- Lint: uv run ruff check . && uv run ruff format .
- Migrate: uv run alembic upgrade head
- Services: docker compose up -d (repo root)

## Rules
- Layering: api -> services -> db. No business logic in api/, no SQL outside db/.
- Every tenant-owned table has tenant_id. Tenant comes from the verified JWT only.
- Runtime uses DATABASE_URL (limited role). Only Alembic uses MIGRATION_DATABASE_URL (owner).
- All DB and network calls are async. Type hints everywhere.
- Small changes only; write or update a test for each new behavior.
- Never read or edit .env.
- Tenant tables are accessed only through get_tenant_session. Never use get_session for them.
- Every new tenant table needs RLS enabled in its migration and a test.
- Only repositories/tenants.py and services/auth.py may use the untenanted get_session, and only for the tenants table. Everything else uses get_tenant_session or tenant_transaction.