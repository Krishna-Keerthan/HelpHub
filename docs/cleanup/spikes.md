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

## C9 Step 0/1 findings (shelved)
C9 steps 2 to 4 (Argon2 and fastembed-import changes) are shelved: hosted embeddings (Cloudflare, pooling "cls") replace the local model in production. Source: Session scratchpad `results/base_a.*`, `results/base_b.*`, `base_*.out`, `an.py`. Image `helphub-backend:c9-base`, 512 MB / 0.1 CPU container, 10 rounds each (5 chat + 1 PDF upload per round), all requests HTTP 200, no OOM kill. Samples: base_a 461 lines, base_b 401 lines (about 1.2 s apart).

| | base_a | base_b |
|---|---|---|
| time to ready (s) | 73.7 | 49.5 |
| idle PSS (MB) | 323.9 | 323.6 |
| per-round peak PSS (MB) | 390.2, 453.3, 453.6, 454.1, 490.4, 490.5, 490.4, 491.0, 489.8, 489.9 | 388.6, 430.0, 431.6, 431.8, 397.3, 442.6, 443.5, 448.2, 449.2, 450.7 |
| cgroup anon at round peak (MB) | 338.4, 338.7, 403.0, 403.5, 448.7, 448.7, 448.7, 449.3, 449.3, 449.3 | 339.5, 384.5, 385.6, 385.8, 386.0, 431.1, 431.3, 431.5, 431.5, 431.6 |
| PSS after idle (MB) | 425.9 | 387.5 |
| max PSS (MB) | 491.0 | 450.7 |

- Structure: anon grows in steps of about 45 to 65 MB (base_a at rounds 3 and 5, base_b at rounds 2 and 6) and then stays flat; it does not return to idle after the load stops (after-idle PSS 387 to 426 MB vs idle 324 MB). The allocator (glibc arenas, fragmentation) was **not measured**, so the cause of the steps is unmeasured.
- Plateau: base_a settles at 489.8 to 491.0 MB, base_b at 442.6 to 450.7 MB. The "447 to 490 MB" range is the span of plateau values over base_a, base_b and the earlier C8 runs. The 447 end is not in the base_a/base_b files: the nearest saved figure is the runbook C8.5 `threads=1` mean peak of 447.8 (docs/deploy/runbook.md); sample counts for the earlier runs are **unmeasured** here. The base_a/base_b counts are the 10 rounds and the sample lines above.
- Run-to-run spread: about 40 MB (base_a plateau minus base_b plateau = 490.4 - 450.7 = 39.7 at the extremes). It is a range from two runs of the same image, not a statistic (n=2, no interval).
- Retained during embedding: about 40 MB stays in the API process during embedding. This figure comes from the Step 1 attribution and is not in the saved result files: **unmeasured** in the data re-read for this entry.
- Argon2 variants (s2_1, s2_2, s2_3): **unmeasured**. s2_1 completed its 10 rounds but the result was lost to a sampler parse error (`ValueError` at bench.py:19, a `/meas/sampler.sh:` line in the samples); s2_2 was stopped at round 7; base_c never became ready (400 s); s2_3 failed on connection after the containers were stopped. No PSS or anon figures exist for these.
- Login latency at 0.1 CPU: **unmeasured**.

### Shelved code and its spec
The uncommitted Argon2/fastembed-import work (app/core/security.py, db/repositories/users.py, services/auth.py, services/embeddings.py, services/users.py, tests/auth/test_auth_flow.py, test_security.py, new tests/auth/test_password_rehash.py) is shelved, saved outside the repo at `~/c9-shelved/` (patch `c9-argon2-fastembed.patch` plus file copies in `files/`). It was never run or tested. `git apply --check -p1` of the patch succeeds against HEAD 02cc7c7. Spec:
- Argon2id with m=19456 KiB, t=2, p=1.
- Async wrappers around hashing and verifying, behind a semaphore of 1 per event loop.
- Rehash only on successful login.
- `DUMMY_HASH` computed with the same parameters.
- Needs an accepted-risk entry (AR-nn, not yet written): during the transition, old hashes cost more than the dummy hash, so login timing leaks whether an account exists with an old hash.
- Side effect to handle: `create_user` would hold the semaphore while holding a DB session.
