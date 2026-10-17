# Review context (read first; ground truth for reviewers)

Multi-tenant support knowledge engine: FastAPI, async SQLAlchemy 2.0, Postgres + pgvector + tsvector + RLS (Postgres-only, no external search engine), Groq. Code is in `backend/`.

## Layering
- `api -> services -> db`. `api/` has no business logic and no SQL; `services/` has no FastAPI imports; `db/` imports neither. `core/` imports none of db, services, api.
- No SQLAlchemy or asyncpg imports outside `db/` (and tests). Import-linter enforces this in the gate; do not re-check by hand.
- Dependency types: `CurrentPrincipal` (short transaction, plain data), `TenantSession`/`CurrentUser` (request-long transaction).

## Tenant rules
- Every tenant-owned table has `tenant_id` and RLS (enabled in its migration, with a test).
- Tenant comes only from the verified JWT (`sub`, `tid`). Never from body, query or headers.
- Runtime uses `DATABASE_URL` (limited role); only Alembic uses `MIGRATION_DATABASE_URL` (owner).
- Tenant tables go through `get_tenant_session` / `tenant_transaction`. Untenanted `get_session` only in `repositories/tenants.py` and `services/auth.py`, for the `tenants` table.
- Search is one SQL query (vector and full-text candidates fused by rank). Each candidate set filters by `tenant_id` in the query itself, and RLS applies on top.

## Transaction and async rules
- All DB and network calls are async. Type hints everywhere.
- Routes that do slow work (embedding, LLM, streaming) use `CurrentPrincipal` and short `tenant_transaction`s, never `TenantSession`. No DB transaction across LLM or embedding calls.
- List queries are bounded (LIMIT/pagination). No blocking calls (`time.sleep`, sync HTTP/file I/O) in `async def`.

## Logging
- Never log document content, tokens, passwords, emails, or raw driver exception messages. Log class name, SQLSTATE, ids, and traceback frames only. No `str(exc)`, `logger.exception`, or `print(` in `app/`.

## Test layout
- `tests/<domain>/` per domain; helpers in `tests/helpers/`; isolation in `tests/isolation/`; end-to-end in `tests/acceptance/`; migrations in `tests/migrations/`; static/security in `tests/security/`, `tests/tooling/`.
- No skip/xfail. No edits to existing tests to make them pass. Default run skips `slow`; before a Day-end commit run `uv run pytest -m "slow or not slow"`. Never run two pytest sessions at once (shared database).

## Gate
- From the repo root: `scripts/gate.sh` (fast, fail-fast, summary on the terminal, details in `/tmp/gate-report.txt`); `scripts/gate.sh --full` also runs the whole test suite.
- The gate covers ruff, format of changed files, import-linter, `alembic check`, skip/xfail scan, forbidden patterns, `# gate-allow: <rule-id> <reason>` format (every allow is listed), a secret scan of tracked files, the accepted-risk register (unique, sequential ids; every `AR-nn` reference exists), `tests/security/`, and pip-audit (warn-only). The first line of `/tmp/gate-report.txt` stamps the commit, time and dirty flag. Reviewers focus on what it cannot see.

## Known and accepted
- See `docs/review/accepted-risks.md` (stable IDs AR-nn). Do not re-report them unless the condition changed.
