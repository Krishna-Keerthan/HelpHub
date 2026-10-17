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

## 5. Render free instance RAM: VERIFIED
Render's compute-plans doc (https://render.com/docs/compute-plans.md), Web service Free: **512 MB RAM, 0.1 CPU** (Render Postgres free: 256 MB, not relevant). The 256 MB figure in the plan sources is therefore not the web-service figure. Spin-down after 15 min idle and 750 free instance hours per workspace per month confirmed on https://render.com/docs/free. (Page text was read through a summarising fetch tool, not a raw copy.)
The instance-types/pricing pages did not list RAM; the compute-plans page did.

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
