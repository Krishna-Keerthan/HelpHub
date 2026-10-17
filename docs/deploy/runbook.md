# Deploy runbook (Render + Supabase)

## Connection defaults
- Both the app (`DATABASE_URL`) and migrations (`MIGRATION_DATABASE_URL`) use the Supabase **session pooler**, port 5432, username `role.<project-ref>`. Measured working with no asyncpg changes (spikes.md section 1).
- If the app is ever moved to the transaction pooler (port 6543), set asyncpg `statement_cache_size=0` in `app/db/session.py`; without it 174 of 180 test transactions failed with SQLSTATE 26000.
- Migrations run only as `helphub_owner`, never as `postgres` (otherwise Supabase grants the API roles access to new tables; spikes.md section 4).

## Supabase role setup (once, as `postgres` over the session pooler)
Pooler usernames are `role.<project-ref>`. `postgres` is not a superuser (CREATEROLE, BYPASSRLS).
```
CREATE ROLE helphub_owner LOGIN PASSWORD '...' NOSUPERUSER NOBYPASSRLS;
CREATE ROLE helphub_app   LOGIN PASSWORD '...' NOSUPERUSER NOBYPASSRLS;
GRANT helphub_owner TO postgres;              -- required for ALTER DEFAULT PRIVILEGES FOR ROLE helphub_owner
GRANT CONNECT, CREATE ON DATABASE postgres TO helphub_owner;
GRANT CONNECT ON DATABASE postgres TO helphub_app;
GRANT USAGE, CREATE ON SCHEMA public TO helphub_owner;
GRANT USAGE ON SCHEMA public TO helphub_app;
ALTER DEFAULT PRIVILEGES FOR ROLE helphub_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO helphub_app;
ALTER DEFAULT PRIVILEGES FOR ROLE helphub_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO helphub_app;
```
Do not rotate a role's password repeatedly while connecting through the pooler: the pooler kept rejecting the new password and repeated failures tripped its circuit breaker (`ECIRCUITBREAKER`, all new connections blocked for minutes).

## Container measurement (C2, 2026-10-17)
Image `backend/Dockerfile` (python:3.12-slim, uv, non-root uid 10001, model baked at `/srv/backend/.cache/fastembed`, one uvicorn process; image 787 MB on disk). Run with `--memory=512m --memory-swap=512m --cpus=0.1`, DB = Supabase session pooler from the dev box, no `GROQ_API_KEY` (so chat streamed an LLM-unavailable response: retrieval and embedding ran, the Groq call did not). Load: register, one text document, then one 10-page PDF upload + 5 concurrent `POST /chat/stream`. Sampler runs inside the container every 100 ms (RSS and PSS of all processes, cgroup `memory.peak`).

| Run | Time to ready | Peak RSS (sum of tree) | Peak PSS (tree) | cgroup peak | PDF upload |
|---|---|---|---|---|---|
| 1 defaults | 54.2 s | 435.4 MB | n/s | 433.0 MB | 422 "PDF took too long to process" |
| 2 defaults | 40.3 s | **743.1 MB** | n/s | 434.1 MB | 422 same |
| 3 `PDF_TIMEOUT_SECONDS=120 PDF_CPU_SECONDS=120` | 56.4 s | 454.3 MB | 440.8 MB | **506.2 MB** | 201 |

- Idle after ready: 333 MB RSS, 321 MB PSS, cgroup 375 to 411 MB. Not OOM-killed in any run.
- The 743 MB in run 2 is a two-process sum with one process at 332 MB while the other was 410 MB; PSS was not sampled in that run. Likely the forked child counting copy-on-write pages before exec, but this was NOT verified. Note the 461 MB rule (90% of 512) is exceeded by that reading.
- cgroup peak includes page cache, so 506 MB is not proof of near-OOM, but there is no margin shown either. Not measured: real Groq streaming, concurrency above 5, PDFs larger than 10 pages, a run on Render itself.
- At 0.1 CPU the default 10 s PDF wall limit is too short for a 10-page, 9,000-character PDF (422 in two of two runs). It completed with the limits raised to 120 s.
- 5 concurrent chat requests took 15 to 22 s each at 0.1 CPU (no LLM call).

## Open items
- [ ] **Render IPv6 to Supabase direct connection: unknown.** Not testable from the dev box. Until answered, do not use the direct host (`db.<ref>.supabase.co`); stay on the session pooler. Test on the first Render deploy and record the result here.
