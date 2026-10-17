# Session A spikes (2026-10-17)

Status key: MEASURED / VERIFIED (source read) / BLOCKED. Nothing here is a guess.

## 1. set_tenant and the Supabase poolers: MEASURED (Session C, 2026-10-17)
- VERIFIED (source): `app/db/tenant_context.py` uses `set_config('app.tenant_id', :tid, true)` (transaction-local).
- MEASURED: 30 concurrent tasks x 6 iterations (180 tenant transactions, 2 tenants, pool_size 5) as `helphub_app`; each iteration checks the tenant sees only its own 3 documents, then that a fresh transaction with no tenant set sees 0 rows on a reused connection. Results (cross-tenant leaks were 0 in every run):

| Pooler | Connect args | Result |
|---|---|---|
| session, 5432 | default (no args) | 180/180 ok |
| session, 5432 | `statement_cache_size=0` | 180/180 ok |
| session, 5432 | + `prepared_statement_cache_size=0` | 180/180 ok |
| session, 5432 | + unique `prepared_statement_name_func` | 180/180 ok |
| transaction, 6543 | default | **6/180 ok; 174 failed, SQLSTATE 26000 (invalid_sql_statement_name)** |
| transaction, 6543 | `statement_cache_size=0` | 180/180 ok |
| transaction, 6543 | + `prepared_statement_cache_size=0` | 180/180 ok |
| transaction, 6543 | + unique `prepared_statement_name_func` | 180/180 ok |

- Conclusion: session pooler needs no change. Transaction pooler needs `statement_cache_size=0` and that alone was sufficient in this workload; the other two settings were not needed. `session.py` passes none today, so only the transaction pooler would need the change. Not measured: longer runs, other query shapes (pgvector ANN, tsvector), SQLAlchemy ORM paths.
- Method note: this is a standalone script with its own engine, not `app.db.session`.

## 2. Render to Supabase direct (IPv6) vs session pooler: OPEN (not testable from here)
- Local only: this WSL2 box reached Supabase through the session pooler (`aws-0-ap-northeast-2.pooler.supabase.com:5432`). Direct (`db.<ref>.supabase.co`) was not tested.
- OPEN: whether a Render free web service can reach Supabase over IPv6. Recorded in `docs/deploy/runbook.md`. Default for both app and migrations: session pooler.

## 3. helphub_owner / helphub_app on Supabase: MEASURED
- As `postgres` (not superuser; CREATEROLE; BYPASSRLS) over the session pooler, `CREATE ROLE helphub_owner` and `helphub_app` (both LOGIN, NOSUPERUSER, NOBYPASSRLS) worked. Pooler usernames are `role.<project-ref>`; both log in.
- Needed grants beyond `docker/postgres/init/01-roles.sh`: `GRANT helphub_owner TO postgres` (required for `ALTER DEFAULT PRIVILEGES FOR ROLE helphub_owner`), `GRANT CREATE, USAGE ON SCHEMA public TO helphub_owner`, `GRANT CREATE ON DATABASE postgres TO helphub_owner`.
- `alembic upgrade head` (0001 to 0009) ran as `helphub_owner` over the session pooler, including `CREATE EXTENSION vector` (lands in `public`, owned by supabase_admin). RLS is enabled on every tenant table; `tenants` has none (by design).
- RLS enforcement: `pytest tests/isolation tests/core` against Supabase through the session pooler as `helphub_app`: **112 passed** (19m41s; about 10 s per test over the WAN). The full suite was started and stopped after about 70 tests because of that latency; the rest of the suite was NOT run against Supabase.

## 4. Tables reachable via the Supabase REST API: NOT reachable (partly tested)
- MEASURED: as `postgres`, `SET LOCAL ROLE anon / authenticated / service_role` then `SELECT count(*)` on all six tenant tables: all denied, SQLSTATE 42501. `information_schema.role_table_grants` shows 0 grants to those roles in `public`. Unauthenticated `GET /rest/v1/` and `/rest/v1/users` return 401.
- NOT tested: requests with the project's real anon/publishable key (not available here).
- Why it holds: tables are created by `helphub_owner`, and Supabase's default privileges for the API roles apply to objects created by `postgres`. HAZARD: running migrations as `postgres` would grant those roles access. Fix if ever needed: `REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated, service_role` plus `ALTER DEFAULT PRIVILEGES ... REVOKE`, or disable the Data API in project settings. Runbook rule: migrations only as `helphub_owner`.

## Incident during spikes
Rotating the helphub_owner password on every run made the pooler reject the new password, and repeated failures tripped its circuit breaker (`ECIRCUITBREAKER`, all new connections blocked for several minutes). The owner password is now fixed for the run (derived from the app password, not stored).

## 5. Render free instance RAM: VERIFIED (raw page, re-checked in B0)
Source: https://render.com/docs/compute-plans.md, fetched raw with curl (HTTP 200), section "Web service plans". The page states it as a table row, not a sentence:
`| 0.1 CPU | 512 MB | [free](free) |  |` (columns: CPU, RAM, Plan ID, Legacy Plan Name).
So the Free web service is **0.1 CPU, 512 MB RAM**. Render Postgres and Key Value free figures are different products and not relevant. Spin-down after 15 minutes and 750 free instance hours per workspace per month: https://render.com/docs/free (read in Session A through a summarising fetch; quote not re-checked raw).

## 6. Full-app peak RSS under load: MEASURED
Setup: local WSL2 box, `uvicorn app.main:app` single process (not a container), local pgvector Postgres + ES running, real Groq calls. Script: register, login, upload a 10-page PDF (`/documents/upload`), POST a ~20 KB text document, then 20 sequential `POST /chat/stream` (all HTTP 200; median 7.1 s, max 10.5 s). RSS polled every 50 ms over the uvicorn process tree.
- Peak tree RSS: **428 MB**; the app process VmHWM at exit: **429 MB**.
- By stage (peak): boot 329 MB, idle 394 MB, upload 426 MB, chat 429 MB.
- Headroom against the 512 MB Free limit: about 83 MB (about 16%). This is a one-user sequential run, no concurrency.
- Caveats (unmeasured): PDF worker subprocess RSS is only included if the 50 ms poll caught it (no child appeared in the final process list; its 512 MB address-space cap is not an RSS figure). ES client is still loaded (removed in A2.2, so the post-cut number will be lower, not re-measured here). Python version / libc differ from the future container. Chat answer quality was not checked, only status codes.
- Residue: one test tenant `spike6-*` remains in the local dev DB; both its documents were deleted through the API.

## Contradiction check against plan decisions
- D4 (fastembed in-process, measure before committing): 429 MB of 512 MB measured; not a contradiction, but thin headroom with 0.1 CPU. Decision stays with the owner; re-measure in Session C inside the container, after the ES cut.
- No spike contradicted D1-D9. Spikes 1-4 could not be run, so D2/D5 assumptions about Supabase remain unverified.

## A2 decisions recorded (2026-10-17)
- `eval-` reserved slug (app/services/auth.py): **stays.** Registration is public until the end of the project, and the Session D eval runner will create throw-away `eval-<hex>` tenants that a cleanup will sweep by slug regex (the moved queries were deleted in B0 as caller-less; recoverable from `pre-lean`). Without the reservation a real tenant could match that regex. Revisit when the runner exists; the gate 0 item 6 exception is this one line.
- ES-bound eval code (guard, run_eval, lifecycle, journal, cleanup) deleted, not kept: owner decision during Session A (plan did not cover it). Recoverable from tag `pre-lean`. Session D rebuilds the slim eval.
- AR-04, 06, 12, 14 are CLOSED tombstone rows (gate_checks requires a gap-free id sequence): AR-12 and AR-14 beyond the plan, because their trigger no longer exists (`/health/db` route deleted in A2.1; the 0007 CHECK dropped by 0008).
