# Session A spikes (2026-10-17)

Status key: MEASURED / VERIFIED (source read) / BLOCKED. Nothing here is a guess.

## 1. set_tenant and the Supabase pooler: PARTLY VERIFIED, live test BLOCKED
- VERIFIED (source): `backend/app/db/tenant_context.py` calls `set_config('app.tenant_id', :tid, true)`; `true` = transaction-local. It resets on commit/rollback.
- VERIFIED (source): `backend/app/db/session.py` passes no `statement_cache_size` to asyncpg. Per the plan's cited Supabase doc, transaction-mode pooling needs `statement_cache_size=0` (asyncpg), and SQLAlchemy's asyncpg dialect also keeps a prepared-statement cache. That is a change the pooler path needs; not done in Session A (no code change outside the A2 cut).
- BLOCKED: RLS isolation test through the pooler. `SPIKE_DATABASE_URL` / `SPIKE_MIGRATION_DATABASE_URL` are not set in this environment.

## 2. Render to Supabase direct (IPv6) vs session pooler: BLOCKED
No Supabase connection strings in the environment; no Render account access from here. Unmeasured.

## 3. helphub_owner / helphub_app on Supabase, isolation tests: BLOCKED
Same reason as 1.

## 4. Tables reachable via Supabase REST API with public keys: BLOCKED
Same reason as 1. Unmeasured.

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
