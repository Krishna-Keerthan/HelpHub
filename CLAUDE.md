# HelpHub
Multi-tenant support knowledge engine. Backend in backend/ (FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL + pgvector; Postgres-only, one search path: pgvector + tsvector). Later: Redis/SAQ, LangGraph, Next.js.

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
- Small changes only. Closed beta: add or update a test only for tenant isolation / RLS, authentication and authorization, AI-provider adapters (embedding, LLM, relevance gate) and the API contract. Everything else is checked by hand and by scripts/smoke_live.py.
- Never read or edit .env.
- Tenant tables are accessed only through get_tenant_session. Never use get_session for them.
- Every new tenant table needs RLS enabled in its migration and a test.
- Only repositories/tenants.py and services/auth.py may use the untenanted get_session, and only for the tenants table. Everything else uses get_tenant_session or tenant_transaction.
- Default pytest skips slow tests (the migration round trip). scripts/gate.sh --full runs them; run it before pushing to main.
- Never log document content, tokens, passwords, or raw exception messages from the DB driver. Log class name, SQLSTATE, ids, and traceback frames (file:line) only.
- Routes that do slow work (embedding, LLM, streaming) use CurrentPrincipal and short tenant_transactions, never TenantSession.
## Tests layout
New tests go in the matching domain directory under tests/; helpers live in tests/helpers/; isolation tests in tests/isolation/.
- After any FastAPI upgrade re-run the 3b mutation (function-scoped TenantSession in the chat route).
- Never commit a failing test: fix it or delete it with a one-line reason in the commit message.
- Run scripts/gate.sh without pipes and check the exit code.
- Never run two pytest sessions at the same time (shared database). The lock is automatic: tests/conftest.py holds an flock on /tmp/helphub-pytest.lock and refuses a second session; scripts/flake_hunt.sh holds it for a whole hunt.

## Review routine
- Before pushing to main: `scripts/gate.sh --full` must be green. `/day-review` is optional; use it only for changes to auth, tenant tables, migrations, upload or the LLM/embedding path.
- `/day-review` runs the gate, then picks reviewer agents by changed paths; agents are read-only.
- Context for reviewers: docs/review/context.md. Accepted risks (stable IDs AR-nn): docs/review/accepted-risks.md; add an entry instead of re-explaining a known risk.
- `.claude/hooks/guard_bash.py` blocks destructive commands (best-effort); do not work around it.
- CI runs on GitHub: ci.yml (gate, audit, image, secrets) on pull requests, pushes to main and manually; frontend.yml on pull requests and pushes to main that touch frontend/**, docs/api/** or its own workflow; db-ops.yml is manual (migrate, backup; backup cannot run while the repo is public). Render and Vercel are deployed (closed beta). Open production-readiness items: docs/deploy/render-checklist.md.
