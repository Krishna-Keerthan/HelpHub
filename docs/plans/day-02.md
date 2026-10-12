# Day 2 plan: auth + tenant RLS + users API, and fixes to the new tests

## Context
Day 1 left models + migrations 0001/0002 (no RLS). New tests (`test_security.py`, `test_rls_coverage.py`, `tests/isolation/`, rewritten `conftest.py`) are red/buggy and ahead of the code. Day 2 implements the pieces they exercise and fixes the test bugs. FastAPI is 0.142.2 (uv.lock); `.env` is not read.

## FastAPI yield-dependency timing (verified in current docs)
- Default `scope="request"`: code after `yield` runs AFTER the response is sent. `scope="function"`: exit code runs after the path function returns but BEFORE the response is sent.
- Consequence: committing after `yield` in a default-scope `get_tenant_session` means the client can get 200/201 and the commit then fail silently (e.g. unique violation at commit, deferred constraint). Exit code cannot change the response.
- Decision: `get_tenant_session` is declared with `Depends(get_tenant_session, scope="function")` (via a shared `TenantSession = Annotated[...]` alias) and commits after `yield`, rolls back on exception and re-raises. Commit errors then become real error responses. Alternative (simpler, explicit): services call `await session.commit()` before returning. Recommend scope="function" + commit in the dependency, because of "one transaction" requirement; note `get_current_user` and `require_admin` sub-dependencies must also be function-scoped (a function-scoped dep can use request-scoped ones, not vice-versa; `get_claims` has no yield so is fine).
- Register is the exception: it has no token, so `register_tenant` runs in its own session/transaction (set_tenant to the new id after inserting the tenant, then admin insert, commit once).

## Steps
1. **config.py**: lowercase fields `jwt_secret`, `jwt_algorithm` (default "HS256"), `access_token_minutes: int = 60` (current `: 60` is an annotation bug; UPPERCASE rename breaks session.py/conftest). Remove trailing blank line.
2. **core/security.py**: pwdlib `PasswordHash((Argon2Hasher(),))`; `hash_password`, `verify_password`, module `DUMMY_HASH = hash_password(<random>)` computed at import; `create_access_token(claims, expires_delta=None)` with `exp`/`iat`; `decode_access_token(token)` using PyJWT with `algorithms=[settings.jwt_algorithm]`, `options={"require": ["exp","sub","tid"]}`, raising a single domain error. Drop python-jose from pyproject (keep only PyJWT).
3. **db/tenant_context.py**: `set_tenant(session, tenant_id: UUID)` -> `SELECT set_config('app.tenant_id', :tid, true)` (transaction-local, so pooled connections can't leak it).
4. **Migration 0003**: `ALTER TABLE users ENABLE ROW LEVEL SECURITY`; `CREATE POLICY tenant_isolation ON users FOR ALL USING (...) WITH CHECK (...)` with `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`, no TO clause; downgrade drops policy + disables RLS. Also confirm the limited role has SELECT/INSERT/UPDATE on users and tenants (check migration 0001/docker init for grants; none in alembic now). No FORCE RLS (owner bypass is needed by the test seeding fixture) — decision recorded.
5. **db/repositories/tenants.py, users.py**: async functions taking session; users functions always `WHERE tenant_id = :tid` as defense-in-depth. tenants repo: `get_by_slug`, `create`. (SQL only in db/, per layering rule.)
6. **schemas/auth.py, schemas/user.py**: `RegisterRequest`, `LoginRequest(tenant_slug,email,password)`, `TokenResponse`, `UserRead` (id, tenant_id, email, role, is_active, created_at; no password_hash), `UserCreate` (email lowercased/validated, password min length, role Literal["admin","agent"]).
7. **services/auth.py**: `register_tenant` (tenant insert -> set_tenant -> admin insert, one transaction, returns user+token), `authenticate` (look up tenant by slug -> set_tenant -> user by email; if tenant or user missing, or inactive, still `verify_password(pw, DUMMY_HASH)` and raise the same `InvalidCredentials`). `services/users.py` for list/get/create (create hashes password; 409 on duplicate email).
8. **api/deps.py**: `get_claims` (`HTTPBearer(auto_error=False)`; missing/invalid/expired -> 401 with `WWW-Authenticate`), `get_tenant_session` (session -> set_tenant from token `tid`, parse UUID, bad -> 401; commit/rollback as above), `get_current_user` (load by `sub` in that tenant; missing/inactive -> 401; sub = user id, not email — tests currently use email), `require_admin` (403).
9. **api/auth.py**: `POST /auth/register`, `POST /auth/login`, `GET /auth/me`. **api/users.py**: `GET /users`, `GET /users/{id}` (404 across tenants, RLS gives no row), `POST /users` (admin). Routers included in `main.py`; routes thin, no SQL/business logic.
10. **Fix tests/conftest.py**: use `settings.database_url` etc.; `owner_conn`, `app_conn` (tx-local `set_config` or rollback+RESET at teardown), `client` (httpx ASGITransport), `make_tenant` helper (owner-connection insert, tracked for cleanup in try/finally via DELETE ... CASCADE), `two_tenants_seeded` built on `make_tenant`. Fix typos (`tenant_is`, `hashed_password`->`password_hash`, misplaced `text(...)` parenthesis, spacing); seed hashes via `hash_password`; remove unused imports and redundant `@pytest.mark.asyncio`; add `tests/isolation/__init__.py`.
11. **Fix tests/auth/test_users_constraints.py**: its `db_session` runs as the limited role, so after migration 0003 inserts need `set_tenant(db_session, tenant.id)` before each user insert (in `make_user` flow / a helper); `make_tenant` there inserts into `tenants` (no RLS) so it still works. Cross-tenant same-email test must switch tenant context between inserts.
12. **Fix tests/auth/test_security.py**: test app functions (hash/verify with DUMMY_HASH, round-trip via `decode_access_token`, expired -> error, tampered signature, wrong alg, forged `alg:none` token built by hand with base64url JSON, missing `exp`/`tid`).
13. **Fix tests/core/test_rls_coverage.py**: add `c.relkind='r'`; GUC name now consistent (`app.tenant_id`) across tests, policy and set_tenant (tests currently use `app.current_tenant_id`).
14. **Fix tests/isolation/test_users_isolation.py**: GUC name; assert RLS error via `exc.orig.__cause__`/sqlstate `42501`; add positive login, no/garbage/expired token 401, cross-tenant UPDATE/DELETE affect 0 rows, `POST /users` happy path as admin, duplicate email 409, response never contains `password_hash`.

## Risks
- Rename of settings attrs breaks `session.py`, `alembic/env.py`, conftest — grep all usages.
- Argon2 at import for `DUMMY_HASH` and in many tests is slow; consider low-cost params only in tests via env.
- `set_config(..., true)` only works inside a transaction; with autobegin it is fine, but any `commit()` mid-request resets tenant context (register flow: set_tenant must come after the tenant insert only if no commit between).
- Timing side channel: DUMMY_HASH must use the same Argon2 params as real hashes.
- Tests run against the dev DB, not an isolated one; leaked rows if cleanup fails.
- Migration 0003 also needs the limited role's grants; absent grants would show as permission errors not RLS errors.
- Login runs before a token exists: tenant lookup must work with no tenant context (tenants has no RLS) but user lookup requires set_tenant first.

## DECISIONS (approved by user, supersede anything above)
- sub = user id; GUC = `app.tenant_id`; commit in a `scope="function"` dependency.
- Register returns a token and respects `ALLOW_PUBLIC_REGISTRATION` (setting; add test for false).
- No grants in 0003, but add a `has_table_privilege` test. Drop python-jose. No RLS on tenants.
- Amendments: (1) `tenant_transaction(tenant_id)` async context manager in db/tenant_context.py; `get_tenant_session` wraps it. (2) lowercase+strip email in all request schemas. (3) password length 12-128. (4) fixtures delete tenants by tracked id only. (5) Never weaken/skip/xfail any test; list every assertion-level change in the report.
- Workflow: first write this plan to `docs/plans/day-02.md` and commit. Then four commits, stopping and reporting after each:
  1. config, security.py, schemas; test_security.py passes.
  2. tenant_context, migration 0003, fix test_users_constraints + conftest; test_rls_coverage passes; alembic up/down/up/check.
  3. repositories, services, deps, /auth endpoints.
  4. /users endpoints; tests/isolation green; full pytest + ruff.
- Future sessions start by reading CLAUDE.md and docs/plans/day-02.md.

## Decisions made during implementation
- JWT carries sub (user id), tid, iat, exp. No role claim; role is read from the DB row on every request.
- Duplicate email: flush happens in users_repo.create, called inside the service try/except, mapped to 409.
- RLS violations are detected by sqlstate 42501.
- Login failure paths all run verify_password against DUMMY_HASH and raise the same InvalidCredentials.

## Open questions (resolved above)
1. JWT `sub`: user id (recommended) vs email? Tests currently use email.
2. GUC name: `app.tenant_id` (your spec) — OK to change tests from `app.current_tenant_id`?
3. Commit location: `scope="function"` dependency commit (recommended) vs commits in services?
4. Should `register` return a token immediately, and is it open (unauthenticated) in all environments?
5. Roles for `limited` DB user: where are grants defined (docker init vs migration)?
6. Drop `python-jose` and use only PyJWT?
7. Add RLS on `tenants` too (it has no `tenant_id`, so the coverage test skips it)?

## Verification
`cd backend && docker compose up -d` (repo root), `uv run alembic upgrade head` then `downgrade -1` and `upgrade head` to verify reversibility; `uv run ruff check . && uv run ruff format .`; `uv run pytest` all green; manually: `uv run fastapi dev app/main.py`, register -> login -> `/auth/me` -> `/users` with two tenants.
