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

## Render environment (free class, 512 MB, 0.1 CPU)
All of these are plain environment variables read by `app/core/config.py` (no code change; `tests/core/test_config_env_overrides.py` covers the PDF ones). Render sets `PORT` (default 10000); the image binds `0.0.0.0:$PORT`.

| Variable | Value | Note |
|---|---|---|
| `APP_ENV` | `production` | hides `/docs`, `/redoc`, `/openapi.json`; startup fails without `GROQ_API_KEY` or with `CORS_ORIGINS=*` |
| `DATABASE_URL` | `postgresql+asyncpg://helphub_app.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres?ssl=require` | session pooler, app role |
| `MIGRATION_DATABASE_URL` | not set on the runtime service | optional for the app; read only by alembic and the test fixtures (raises if read while unset) |
| `JWT_SECRET` | 32+ random characters | rejected if it is the `.env.example` placeholder |
| `GROQ_API_KEY` | secret | required when `APP_ENV=production` |
| `CORS_ORIGINS` | frontend origin(s), comma-separated | empty = no CORS headers |
| `ALLOW_PUBLIC_REGISTRATION` | `false` (default) | flipped to `true` as the very last project step |
| `PDF_TIMEOUT_SECONDS` | `120` | raised from 10: at 0.1 CPU a 10-page PDF exceeded 10 s in 2 of 2 runs. 120 is the starting value; C7 records the real extraction time |
| `PDF_CPU_SECONDS` | unset (stays 10) | CPU time, not wall time; kernel `RLIMIT_CPU` backstop |
| `PDF_MAX_CONCURRENCY` | `1` | a second concurrent upload waits `PDF_QUEUE_WAIT_SECONDS` (5 s) and then gets 503 |
| `READY_TIMEOUT_SECONDS` | unset (stays 5) | how long `/health/ready` waits for `SELECT 1` before 503; raise it only if readiness flaps under load |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | `15` / `7` (defaults) | |
| `RATE_LIMIT_*` | defaults | login 5 per account and 30 global per 60 s; search 60 and chat 10 per user per 60 s; in-process (AR-13, AR-19) |

## Creating tenants (registration is closed)
From `backend/`, with `DATABASE_URL` (app role, session pooler), `MIGRATION_DATABASE_URL` and `JWT_SECRET` set in the shell:
`SEED_ADMIN_PASSWORD=... uv run python scripts/seed_tenant.py --name "Acme" --slug acme --email admin@acme.test`
(omit the variable to be prompted). `scripts/` is not in the image; run it from a checkout.

## Migrations
Run `uv run alembic upgrade head` with `MIGRATION_DATABASE_URL` = `helphub_owner.<ref>` over the session pooler, from a dev machine or a CI job; never as `postgres` and never from the app's runtime role. `.github/workflows/ci.yml` runs tests only; a deploy-time migrate job is NOT built (deploy session). Migration 0010 adds `refresh_tokens` (RLS in the same migration).

## VERIFY items from the plan (checked 2026-10-17)
| Item | Status | Evidence |
|---|---|---|
| Render free tier pre-deploy command | **VERIFIED: not available**, so migrations run from CI or a dev machine | "The pre-deploy command is available for paid web services, private services, and background workers." https://render.com/docs/deploys (section Pre-deploy command, raw page `deploys.md`) |
| Time a service has to bind its port / pass health checks after start | **VERIFIED: 15 minutes**, far above the measured 40 to 56 s, so warm-up stays blocking (no code change) | "If this condition is not met within 15 minutes, Render cancels the deploy and continues routing traffic to your service's existing instances." https://render.com/docs/health-checks (Handling failures, New deploy); start command timeout "15 minutes" https://render.com/docs/deploys. The port-binding section states no time limit, only "If Render fails to detect a bound port, your web service's deploy fails" https://render.com/docs/web-services |
| Does the "60 seconds of failed health checks restarts the instance" rule apply while the instance is still starting | **UNVERIFIED** | The rule is documented for "a running service instance" (https://render.com/docs/health-checks). Our measured start is 40 to 56 s on a dev box; Render's CPU may be slower. Watch the first deploy |
| Free web service wake-up time | **VERIFIED (Render's figure)**: "This process takes about one minute." https://render.com/docs/free | Our own startup (40 to 56 s measured) is on top of or part of that: not measured on Render |
| Uptime bot free interval | **VERIFIED for UptimeRobot**: Free plan, 5 minutes, 50 monitors (under the 15-minute spin-down) https://uptimerobot.com/pricing.md | Free-plan terms for a non-personal project not checked: UNVERIFIED |
| Supabase pause rule | **VERIFIED**: "Free projects are paused after 1 week of inactivity." https://supabase.com/pricing ; "A Free plan project is considered inactive if it does not receive sufficient user database activity over the past week." https://supabase.com/docs/guides/platform/free-project-pausing | |
| Does `SELECT 1` from `/health/ready` count as database activity | **UNVERIFIED** | The doc says "user database activity" and "user queries" without defining them. Test = leave the project idle past the limit. Cheap hedge: a scheduled CI job doing a real read of a table |
| Render free RAM | **VERIFIED 512 MB** (spikes.md section 5) | |
| Backups | **GAP, not built**: Supabase free has none. Options: scheduled `pg_dump` from CI to storage you control, or state the gap in the README | deploy session |

## C7 re-measurement (2026-10-17): criteria NOT met
Setup: image built from commit db09187's app code, `--memory=512m --memory-swap=512m --cpus=0.1`, real Groq streaming, DB = Supabase session pooler from the dev box (WAN latency included), `APP_ENV=production`, `PDF_TIMEOUT_SECONDS=120`, `PDF_CPU_SECONDS` at its default 10, `RATE_LIMIT_*_PER_USER` raised so the limiter did not interfere. A sampler inside the container (every 0.2 s) sums PSS over all processes; `anon` comes from `memory.stat` at the PSS peak. One round = login, then concurrently 5 chat requests and N PDF uploads (N = `PDF_MAX_CONCURRENCY`), each PDF 10 pages and unique. 10 rounds per setting. The sampler itself competes for the 0.1 CPU.

| | PDF concurrency 1 | PDF concurrency 2 |
|---|---|---|
| Rounds completed | 10 of 10 | 1 of 10 (container OOM-killed during round 2; reproduced in 2 of 2 attempts) |
| Time to ready (`/health`, `/health/ready`) | 70.0 s, 77.2 s | 73.5 s and 76.1 s (two attempts), 83.4 s and 86.1 s |
| PSS peak at startup (model load) | 453.5 MB | not recorded (sampler data lost with the container) |
| PSS peak per round | 478.7 to 521.2 MB in rounds 2 to 10; round 1 reported 679.6 MB | not recorded |
| `anon` at PSS peak | 435 to 509 MB (500 to 509 MB in rounds 6 to 10) | not recorded |
| cgroup `memory.events` | `oom_kill 0`, `max` 1017 (limit reached 1017 times) | `oom_killed=true`, exit 137 |
| Chat: 200 with an answer / sent | 50 / 50 (median 24.8 s, max 57.8 s) | 5 / 5 in round 1 |
| PDF upload (whole request, under chat load) | 201 x9, 500 x1 (round 8, 28.8 s, cause NOT captured: container logs were not saved for this run); 201 times 104.7 to 148.3 s, median 106.8 s | 160.4 s and 169.2 s (round 1) |
| PDF extraction alone, idle container at 0.1 CPU (3 runs) | 15.7 s, 10.5 s, 15.7 s (9,018 characters) | n/a |

Against the criteria fixed in advance:
- **PSS peak at most 461 MB: FAIL.** Steady-state rounds peaked at 512 to 521 MB. The 679.6 MB (and 872 MB RSS in round 4) readings coincide with a forked child (`uname -p`, spawned by Python before exec) sampled while the 329 MB parent was also sampled; the reading is not atomic, so those two are probably artifacts. Not verified. The steady 500 MB `anon` figure is a separate measurement and agrees with 512 MB being reached.
- **oom_kill 0: PASS for concurrency 1, FAIL for concurrency 2.**
- **PDF upload succeeds at a wall timeout of 120 s or less:** extraction alone (10.5 to 15.7 s) is well inside 120 s. Whole uploads under chat load took up to 148.3 s, and one of 10 returned 500 with an unknown cause. Not demonstrated.
- The cgroup sat at its 512 MB limit and reclaimed 1,017 times; round 9 of the concurrency-1 run took 325 s. Plausibly reclaim thrash, not verified.

Two defects seen in the container log (found during C7; the first is fixed in C8.2, see below):
- `Ignoring corrupted tree cache file ... [Errno 13] Permission denied` under `/srv/backend/.cache/fastembed`: the baked model cache is not accessible as the non-root user for writes. It loaded and worked (HF_HUB_OFFLINE=1).
- `readiness check failed: error=TimeoutError` once, during load (the 5 s `SELECT 1` timeout at 0.1 CPU).

Options (not chosen, for the owner): a larger instance class or CPU share; a smaller or lazily loaded embedding model; lower PDF limits (smaller `pdf_memory_bytes`, fewer pages) and PDF concurrency 1; moving PDF extraction out of the web process; fewer concurrent chats per instance; accept the free class for a demo with concurrency 1 and a documented 500-or-slow tail.

## C8 follow-up (2026-10-19)
Measurement setup for all C8 numbers: image built from the repo, `--memory=512m --memory-swap=512m --cpus=0.1`, scratch Postgres 16 + pgvector in a sibling container on the same Docker network (migrated with `alembic upgrade head` from the image; **no WAN latency**, unlike C7's Supabase pooler), Groq replaced by a local stub that streams 60 chunks (**no real Groq**: the key lives in `.env`, which is off limits). Absolute times therefore differ from C7; compare within C8 only.

### C8.2 baked model cache readable by the app user
- Cause: `huggingface_hub` wrote `trees/*.json` as mode 600 root; the `app` user (uid 10001) got `Errno 13` and logged "Ignoring corrupted tree cache file". Fix: `chmod -R a+rX,go-w /srv/backend/.cache` in the build stage (`backend/Dockerfile`). CI now asserts no cache file lacks the world-read bit (the check finds 1 file on the old image, 0 on the new).
- Model not downloaded at start: container started with `--network none` reached "Application startup complete"; `docker diff` empty and the cache file listing (path, size, mtime) identical before and after start. `HF_HUB_OFFLINE=1` is also set.
- Time to ready (`docker run` to first `/health` 200), local DB, 0.1 CPU: before 43.8, 45.8, 44.3 s (mean 44.6); after 41.8, 42.4, 43.3 s (mean 42.5). Difference of about 2 s with n=3 each; not shown to be more than noise.
- Still logged at start, not changed: onnxruntime `Failed to persist telemetry device ID; using an in-memory identifier` (a warning, not a failure).

## Open items
- [ ] **Render IPv6 to Supabase direct connection: unknown.** Not testable from the dev box. Stay on the session pooler until answered; test on the first Render deploy and record the result here.
- [x] **`MIGRATION_DATABASE_URL` is optional for the app** (C8): leave it unset on the runtime service; set it only where `alembic upgrade head` runs. Never put the owner URL on the runtime service.
- [ ] **Client IPs behind Render's proxy** are not trusted (uvicorn runs without `--proxy-headers`), which is why login limits are per account, not per IP (AR-19).
- [ ] **Live smoke script** (register or seed, upload, search, chat, delete against the deployed URL): not built.
- [ ] **Uptime bot** and the keep-alive target (`GET /health/ready`): not configured. When it is: set it to alert only after 2 consecutive failures (tolerate one). C7 saw one `/health/ready` timeout under load at 0.1 CPU (the 5 s `SELECT 1` limit), so a single failed probe is expected noise, not an outage.
- [ ] **Render's health check path must be `/health`** (liveness, touches nothing else), not `/health/ready`. Reason: a database blip or a slow `SELECT 1` on a busy 0.1 CPU instance would otherwise count against the instance, and Render restarts an instance after 60 s of failed checks (https://render.com/docs/health-checks, quoted in the table above). `/health/ready` is for the uptime bot and the Supabase keep-alive only.
- [ ] **Memory gate (Gate 0 item 7) is OPEN and the C7 criteria failed**: see the C7 section above. No instance class, model or architecture change has been made.
