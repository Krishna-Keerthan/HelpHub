# Deploy runbook (Render + Supabase)

## Status on 2026-10-24
CI, Supabase and demo-data lines are as reported by the owner; this update did not check them against GitHub or Supabase.
- CI is green. Supabase is at migration 0012. The demo tenant, a viewer user and 24 documents are seeded on Supabase (20261024).
- `backend/scripts/smoke_live.py` exists; it has not been run against Render.
- `.github/workflows/db-ops.yml` exists (manual dispatch, jobs `migrate` and `backup`). `render.yaml` does not exist.
- **Render itself is unmeasured.** Every memory and timing figure below came from local Docker with emulated limits (`--memory=512m --cpus=0.1`), not from a Render instance.
- The C2, C7 and C8 sections measure the **local fastembed model** (in-process ONNX). Production now uses Cloudflare embeddings (`EMBEDDING_PROVIDER=cloudflare`, AR-20); see "Cloudflare-embedding plateau" near the end.

## Connection defaults
- Both the app (`DATABASE_URL`) and migrations (`MIGRATION_DATABASE_URL`) use the Supabase **session pooler**, port 5432, username `role.<project-ref>`. Measured working with no asyncpg changes (spikes.md section 1).
- If the app is ever moved to the transaction pooler (port 6543), set asyncpg `statement_cache_size=0` in `app/db/session.py`; without it 174 of 180 test transactions failed with SQLSTATE 26000.
- The Supabase dashboard shows `postgresql://...`; add `+asyncpg` (`postgresql+asyncpg://...`) before pasting it, because the app refuses to start with any other prefix.
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
pgvector must live in schema `public`: create it as `postgres` with the SQL `create extension vector with schema public`. The dashboard toggle installs it in schema `extensions`, where `to_regtype('vector')` is null for `helphub_owner` and `helphub_app` (search_path is `"$user", public`) and `helphub_owner` (not a superuser) cannot create it itself because the extension is not trusted. Migration 0001's `CREATE EXTENSION IF NOT EXISTS vector` is a no-op once it exists.
Migrations are run from a copy of the tracked files with no `.env` (`git archive HEAD backend | tar -x -C <dir>`), with `MIGRATION_DATABASE_URL` and the other settings variables in the shell environment, because `alembic/env.py` loads `app.core.config.settings`, which reads `.env` if one exists.

Do not rotate a role's password repeatedly while connecting through the pooler: the pooler kept rejecting the new password and repeated failures tripped its circuit breaker (`ECIRCUITBREAKER`, all new connections blocked for minutes).

### Platform behaviour: Supabase auto-enables RLS on new tables (verified 2026-10-20)

An enabled event trigger `ensure_rls` (event `ddl_command_end`) calls the function `rls_auto_enable`. Every table created in the database gets `ENABLE ROW LEVEL SECURITY` with no policy, including `alembic_version`, `tenants` and `users` (verified by a query run by the user on Supabase). A local Postgres has no such trigger.

Effect before migration 0011: `tenants` had RLS on and no policy, so `helphub_app` was denied (`new row violates row-level security policy for table "tenants"`). `scripts/seed_tenant.py` failed this way with nothing written. Locally RLS was off and the owner is a superuser, so the same code passed.

The body of `rls_auto_enable` has not been read by us; the user may add it here. Until then, do not assume what else it does.

Resolution (in the repo): migration `0011_tenants_rls.py` enables RLS on `tenants` with explicit policies `TO helphub_app` for SELECT and INSERT only (the commands the app runs; no UPDATE or DELETE policy, no FORCE). `tests/migrations/test_rls_invariant.py` requires every table in `public` except `alembic_version` to have RLS enabled and at least one policy. Local, CI and Supabase now behave the same. Because there is no FORCE, the owner bypasses RLS: the runtime service must never get `MIGRATION_DATABASE_URL` (see AR-21).

## Container measurement (C2, 2026-10-17) — LOCAL-model baseline
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

## Seeding the hosted demo tenant
Prerequisite: the hosted tenant and its admin already exist (see "Creating tenants"). Run this in a SEPARATE terminal opened only for this job, from `backend/`.

**How it works.** `scripts/create_viewer.py` and `scripts/load_demo_corpus.py` are plain HTTP clients (httpx). They log in with `POST /auth/login` and then call `POST /users` (create_viewer) or `GET /documents`, `POST /documents/upload`, `GET /documents/{id}` (load_demo_corpus). They never touch the database. So a locally running app, started with the hosted `DATABASE_URL`, is required: the app embeds the uploads and writes to the hosted database. (Alternative not covered here: point `BASE_URL` at the Render service and skip the local app. Embedding then runs on the 0.1 CPU instance.)

| Variable | Used by | Source |
|---|---|---|
| `DATABASE_URL` (app role, `helphub_app`) | the local app | `~/.helphub-supabase.env` |
| `JWT_SECRET` | the local app | `~/.helphub-supabase.env` |
| `BASE_URL` (`http://127.0.0.1:8001`), `TENANT_SLUG`, `EMAIL`, `PASSWORD` (hosted tenant admin) | both scripts | `~/.helphub-hosted-creds` (below) |
| `VIEWER_EMAIL`, `VIEWER_PASSWORD` | create_viewer only | typed into the shell, environment only |

`MIGRATION_DATABASE_URL` is never exported here. The app does not need it at runtime.

**Credentials files.** `~/.helphub-local-creds` is the LOCAL database's admin and is never used here. The scripts read it as a fallback for any of `BASE_URL`, `TENANT_SLUG`, `EMAIL`, `PASSWORD` that is not in the environment, so this terminal exports all four from `~/.helphub-hosted-creds` (mode 600, `KEY=VALUE` lines, same four keys) and the fallback is never reached. Create it yourself; no script writes it. As of 2026-10-24 `~/.helphub-supabase.env` holds only `JWT_SECRET`: add a `DATABASE_URL=` line (the app-role session-pooler URL, `postgresql+asyncpg://...`) before the steps below, or the export step fails.

**Caveat on `.env`.** The app still reads `backend/.env` for settings the shell does not set. Exported variables take precedence, so `DATABASE_URL` and `JWT_SECRET` come from the shell. Do not edit `.env` for this job.

```bash
cd ~/projects/helphub/backend

# 1. Export only DATABASE_URL and JWT_SECRET (nothing else from the file).
for k in DATABASE_URL JWT_SECRET; do
  v=$(grep -E "^(export +)?$k=" ~/.helphub-supabase.env | tail -1 \
      | sed -E "s/^(export +)?$k=//; s/^['\"]//; s/['\"]$//")
  [ -n "$v" ] || { echo "missing $k in ~/.helphub-supabase.env"; return 1 2>/dev/null; }
  export "$k=$v"
done
unset v MIGRATION_DATABASE_URL

# 2. Hosted tenant admin (all four keys, so ~/.helphub-local-creds is not used).
for k in BASE_URL TENANT_SLUG EMAIL PASSWORD; do
  v=$(grep -E "^$k=" ~/.helphub-hosted-creds | tail -1 \
      | sed -E "s/^$k=//; s/^['\"]//; s/['\"]$//")
  [ -n "$v" ] || { echo "missing $k in ~/.helphub-hosted-creds"; return 1 2>/dev/null; }
  export "$k=$v"
done
unset v
case "$BASE_URL" in http://127.0.0.1:8001|http://localhost:8001) ;; *) echo "BASE_URL must be the local app on :8001" ;; esac

# 3. Check where the database variables point. Expected in THIS terminal only:
#    DATABASE_URL (environment): hosted; MIGRATION_DATABASE_URL (environment): unset;
#    the two ".env only" lines: local. Exit code 1 is expected. In any other terminal
#    a "hosted" result is a stop sign.
uv run python scripts/check_local_db.py

# 4. Start the app on a port (no reload) and wait until it is ready.
uv run fastapi run app/main.py --host 127.0.0.1 --port 8001 &
APP_PID=$!
until curl -fsS http://127.0.0.1:8001/health/ready >/dev/null 2>&1; do sleep 2; done

# 5. Viewer, then corpus. Both are idempotent (existing viewer / existing titles are skipped).
read -r -p "viewer email: " VIEWER_EMAIL; read -r -s -p "viewer password: " VIEWER_PASSWORD; echo
export VIEWER_EMAIL VIEWER_PASSWORD
uv run python scripts/create_viewer.py       # prints created=N existing=N conflicts=N
uv run python scripts/load_demo_corpus.py    # prints files= uploaded= skipped= failed= not_ready=
```

Expect `conflicts=0` and `failed=0 not_ready=0`. Exit 0 from both scripts means success; a rerun should show `created=0 existing=1` and `uploaded=0 skipped=<files>`.

**Closing the terminal.** Never run `pytest`, `scripts/gate.sh` or `scripts/flake_hunt.sh` in this terminal: this shell holds the hosted `DATABASE_URL`. When done:

```bash
kill "$APP_PID"; wait "$APP_PID" 2>/dev/null
ss -ltn 'sport = :8001'        # must list nothing
unset DATABASE_URL JWT_SECRET BASE_URL TENANT_SLUG EMAIL PASSWORD VIEWER_EMAIL VIEWER_PASSWORD APP_PID
exit                           # close the terminal; do not reuse it
```

## Migrations
Run `uv run alembic upgrade head` with `MIGRATION_DATABASE_URL` = `helphub_owner.<ref>` over the session pooler, from a dev machine or a CI job; never as `postgres` and never from the app's runtime role. `.github/workflows/ci.yml` runs tests only. A manual `migrate` job exists in `.github/workflows/db-ops.yml` (workflow_dispatch, environment `production`, secret `MIGRATION_DATABASE_URL`); it is not triggered by a deploy, and whether it has been run is not recorded here. Migration 0010 adds `refresh_tokens` (RLS in the same migration).

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

## C7 re-measurement (2026-10-17): criteria NOT met — LOCAL-model baseline
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

## C8 follow-up (2026-10-19) — LOCAL-model baseline
Measurement setup for all C8 numbers: image built from the repo, `--memory=512m --memory-swap=512m --cpus=0.1`, scratch Postgres 16 + pgvector in a sibling container on the same Docker network (migrated with `alembic upgrade head` from the image; **no WAN latency**, unlike C7's Supabase pooler), Groq replaced by a local stub that streams 60 chunks (**no real Groq**: the key lives in `.env`, which is off limits). Absolute times therefore differ from C7; compare within C8 only.

### C8.2 baked model cache readable by the app user
- Cause: `huggingface_hub` wrote `trees/*.json` as mode 600 root; the `app` user (uid 10001) got `Errno 13` and logged "Ignoring corrupted tree cache file". Fix: `chmod -R a+rX,go-w /srv/backend/.cache` in the build stage (`backend/Dockerfile`). CI now asserts no cache file lacks the world-read bit (the check finds 1 file on the old image, 0 on the new).
- Model not downloaded at start: container started with `--network none` reached "Application startup complete"; `docker diff` empty and the cache file listing (path, size, mtime) identical before and after start. `HF_HUB_OFFLINE=1` is also set.
- Time to ready (`docker run` to first `/health` 200), local DB, 0.1 CPU: before 43.8, 45.8, 44.3 s (mean 44.6); after 41.8, 42.4, 43.3 s (mean 42.5). Difference of about 2 s with n=3 each; not shown to be more than noise.
- Still logged at start, not changed: onnxruntime `Failed to persist telemetry device ID; using an in-memory identifier` (a warning, not a failure).

### C8.4 memory attribution (PSS, MB, whole process tree)
Method: one Python process in the container (`--memory=512m --memory-swap=512m --cpus=0.1`, uid 1000, `WARM_UP_EMBEDDINGS=false`), PSS read from `/proc/<pid>/smaps_rollup` for the process and all its children at the end of each stage; "peak" is the maximum of a 0.1 s sampler thread during the stage. Stages 6 and later go through the real app via an in-process ASGI client (no uvicorn HTTP layer, no concurrency), stub LLM, local DB. Two full runs; both settled values shown (run 1 / run 2).

| Stage | PSS settled | Added by stage | Peak during stage |
|---|---|---|---|
| 1 interpreter start | 14.4 / 14.6 | | |
| 2 after imports (`app.api.*`, services) | 89.5 / 89.3 | +75.1 / +74.7 | 111.8 / 111.8 |
| 3 after app creation (`import app.main`) | 89.6 / 89.3 | +0.1 / 0.0 | |
| 4 after first DB pool use (`SELECT 1`) | 91.3 / 91.0 | +1.7 / +1.7 | |
| 5 after warm-up (fastembed import + model load) | 321.5 / 320.5 | **+230.2 / +229.5** | |
| 6 after one embedding (query) | 323.1 / 322.1 | +1.6 / +1.6 | |
| 7 extra: register + login (Argon2) | 333.7 / 333.0 | +10.6 / +10.9 | **397.7 / 397.1** (+64) |
| 8 extra: one text document ingest | 334.8 / 334.1 | +1.1 / +1.1 | |
| 9 after one chat (stub LLM, 3,178 bytes) | 336.5 / 335.7 | +1.7 / +1.6 | |
| 10 after one 10-page PDF upload (includes embedding its chunks) | 374.9 / 377.0 | **+38.4 / +41.3** | 375.7 / 377.0; extraction child alone 27.6 (run 2, sampled) |
| 11 two seconds later | 374.9 / 377.0 | 0 | |

- **The stage that adds the most is warm-up (fastembed import plus loading the ONNX model): about +230 MB, 70% of the 321 MB at ready.** Imports are second (+75 MB). Among request-time stages the PDF upload is the largest (+38 to +41 MB settled, not released afterwards).
- The PDF stage mixes extraction (child process, at most 27.6 MB sampled) with embedding its chunks in the parent; this run does not separate the parent's growth between them.
- Argon2 (register or login) adds a transient 64 MB peak (+10 MB retained). Importing `app.core.security` also hashes a dummy password at import (`DUMMY_HASH`), visible as the 111.8 MB peak in stage 2.
- Single request at a time. Concurrent chats, several documents and a longer-lived process are not in this table (C8.6 covers load).

### C8.5 one lever at a time (2026-10-19; NOT committed, see status)
Setup as C8.4 but the real uvicorn server: one container under `--memory=512m --memory-swap=512m --cpus=0.1`, local DB, stub LLM, a 1 s PSS sampler inside the container (python and uvicorn processes, children included). One run = start, 12 s idle, 3 rounds of (login, then 5 chats and 1 unique 10-page PDF at once), 6 s idle. The first attempt at this batch ran two copies of the script at once (shared container name and port) and was discarded entirely; the numbers below are from clean single runs. A fourth container run (threads1b) died with the Docker daemon (below) and is not counted.

| Run | Lever | Time to ready (s) | Idle PSS (MB) | Round peak PSS, rounds 1/2/3 (MB) | PSS 6 s after load (MB) | oom_kill |
|---|---|---|---|---|---|---|
| base1 | none (serve wrapper = image CMD) | 43.2 | 322.8 | 388.0 / 437.6 / 438.6 | 419.7 | 0 |
| base2 | none | 44.3 | 322.5 | 388.3 / 452.5 / 453.9 | 435.0 | 0 |
| base3 | none | 43.3 | 323.0 | 389.1 / 453.5 / 499.6 | 435.7 | 0 |
| cmd_unmodified | image CMD as shipped (single uvicorn, no reload, no workers flag) | 43.6 | 322.8 | 388.6 / 452.7 / 498.5 | 434.8 | 0 |
| threads1 | `TextEmbedding(threads=1)` | 42.1 | **310.9** | 377.4 / 441.6 / 442.1 | **378.3** | 0 |
| malloc2 | `MALLOC_ARENA_MAX=2` | 43.1 | 322.0 | 387.1 / 432.6 / 433.1 | 369.3 | 0 |
| malloc2b | `MALLOC_ARENA_MAX=2` | 35.9 | 322.2 | 387.4 / 433.0 / 433.2 | 413.5 | 0 |
| noarena | `TextEmbedding(enable_cpu_mem_arena=False)` | 41.8 | 310.6 | 412.1 / 474.8 / **521.1** | 451.3 | 0 |
| pool2 | engine `pool_size=2, max_overflow=0` | 43.1 | 323.2 | 388.4 / 434.2 / 435.0 | 416.2 | 0 |

Library documentation quoted (fastembed 0.9.0, `TextEmbedding.__init__` docstring): "threads (int, optional): The number of threads single onnxruntime session can use. Defaults to None." The code sets `intra_op_num_threads` and `inter_op_num_threads` to it. `enable_cpu_mem_arena` is the only exposed ONNX session option (`EXPOSED_SESSION_OPTIONS = ("enable_cpu_mem_arena",)`), passed as a keyword argument.

Reading (baseline idle is very stable, 322.5 to 323.0; baseline round-3 peak is NOT: 438.6, 453.9, 499.6, 498.5, a 61 MB spread, so single runs cannot show a 10 MB peak effect):
- **Single uvicorn worker, no reload**: no effect, because it is already the shipped configuration (cmd_unmodified matches the baselines). Nothing to change.
- **DB pool size 2/0**: no effect (idle +0.4, peak within baseline range). Not kept.
- **ONNX memory arena off**: idle -12.2 but peaks +22 to +67 over the baselines (round 3: 521.1) and slower first round. Worse for the peak criterion. Not kept.
- **threads=1**: idle -11.9 MB (n=1; baseline n=4), peak inside the baseline range, PSS after load 378.3 vs 419.7 to 435.7. Meets the 10 MB rule on idle, but from ONE complete run (the repeat was lost). Candidate.
- **MALLOC_ARENA_MAX=2**: idle unchanged; round-3 peak 433.1 and 433.2 (n=2) vs baseline mean 472.7, i.e. -39.5 MB against the mean but only -5.5 MB against the lowest baseline (438.6). All 2 malloc runs are below all 4 baselines (chance of that with no effect: 1 in 15). After-load PSS 369.3 and 413.5. Candidate, not conclusive.
- Not applied to the code or Dockerfile: the confirmation runs could not be completed (below).
- Chat latency in the loaded rounds (7 to 11 s, stub LLM) and PDF (42 to 70 s whole request under load) did not differ between levers beyond run-to-run spread.

Status: the Docker daemon (Docker Desktop, WSL integration) stopped during the third repeat batch (`docker info` now crashes with SIGBUS), so C8.5 repeats (base4, malloc2c, threads1b/c) and the whole of C8.6 were not run, and the gate cannot start its Postgres. This section is therefore uncommitted work.

### C8.5b screening, 5 runs per condition (2026-10-19)
Same harness as C8.5, 3 rounds per run, 20 runs one container at a time, order rotated each run (ABCD, BCDA, CDAB, DABC, DCBA). Stub LLM, local DB, 0.1 CPU, 512 MB. Every chat 200, every PDF 201, `oom_kill 0` in all 20. Rule fixed beforehand: adopt if (a) mean round-3 peak is at least 10 MB below baseline's mean AND the worst run is not above baseline's worst, or (b) idle is at least 10 MB lower in all runs; otherwise "no demonstrated effect".

| Condition | Idle PSS mean (range) | Round-3 peak mean (min to max) | PSS after load mean (range) | Verdict |
|---|---|---|---|---|
| baseline | 323.6 (322.7 to 324.3) | 470.5 (435.8 to 498.5) | 422.9 (409.0 to 435.5) | |
| `MALLOC_ARENA_MAX=2` | 322.5 (322.2 to 323.1) | 466.3 (433.7 to 497.0) | 411.4 (387.9 to 433.1) | no demonstrated effect (peak -4.2, idle -1.1) |
| `threads=1` | **309.8** (307.3 to 311.5) | **447.8** (431.5 to 485.0) | 402.2 (374.6 to 423.6) | **adopt**: (a) peak -22.7, worst 485.0 <= 498.5; (b) idle -12 to -16 in 5 of 5 |
| both | 310.7 (301.9 to 321.7) | 447.9 (432.4 to 476.0) | 384.0 (368.8 to 412.0) | meets (a), but nothing beyond threads=1 alone; malloc part has no effect |

Adopted: `threads=1`. fastembed has no environment variable for it, so it is `EMBEDDING_THREADS` (a setting, default unset = library default) and `ENV EMBEDDING_THREADS=1` in the Dockerfile. Rejected levers stay recorded: `MALLOC_ARENA_MAX=2`, ONNX arena off (C8.5), pool 2/0 (C8.5), single worker (already the case).
**Correction (C8.5c below): the idle gain in this table was largely an artifact of the test wrapper, which imported `fastembed` in the main thread for the `threads=1` and `both` runs. The threads=1 effect on the shipped code is smaller than this table shows.**

### C8.3b what the model-load step is made of (report only, no change)
One process, same limits, `/proc/self/smaps_rollup` (MB):

| | Rss | Pss | Pss_Anon | Pss_File |
|---|---|---|---|---|
| before (interpreter) | 25.0 | 25.0 | 15.7 | 9.3 |
| after `import app.services.embeddings` | 34.6 | 34.6 | 19.3 | 15.3 |
| after warm-up | 266.2 | 266.2 | 223.9 | 42.3 |

Warm-up adds 204.6 MB anon and 27.0 MB file-backed. On disk the cache holds one 66.5 MB ONNX file plus a 0.7 MB file (67.2 MB of regular files). So the anonymous memory is about 3 times the model file size; what it consists of was not measured.

### C8.5c control for the wrapper artifact (2026-10-19)
3 runs each, order rotated, 3 rounds, same harness. "Import-only" = test wrapper imports `fastembed` in the main thread, nothing else changed (image without the threads setting). "Wrapper threads=1" = the screening wrapper. "Real" = the shipped code, `EMBEDDING_THREADS=1` from the Dockerfile ENV, image CMD, no wrapper.

| Condition | Idle PSS (MB) | Round-3 peak (MB) | PSS after load (MB) |
|---|---|---|---|
| baseline (C8.5b, n=5) | 323.6 (322.7 to 324.3) | 470.5 (435.8 to 498.5) | 422.9 |
| import-only | 308.8, 312.1, 312.0 | 457.5, 469.1, 440.8 | 393.6, 405.2, 376.8 |
| wrapper threads=1 | 312.3, 309.2, 311.8 | 443.1, 428.6, 469.8 | 379.3, 364.7, 403.2 |
| real threads=1 | 314.7, 314.9, 314.6 | 444.7, 445.7, 488.8 | 425.8, 426.6, 425.1 |
| real threads=1, C8.6 run | 323.5 | 439.7 (round 3) | 422.0 |

- Importing fastembed in the main thread alone lowers idle by 10.6 to 15.5 MB in 3 of 3 runs vs the baseline range; it matches the wrapper's threads=1 result, so that gain was not from threads.
- The shipped threads=1 code: idle 314.6 to 314.9 in 3 runs (-9 vs baseline mean, below the 10 MB bar) but 323.5 in the C8.6 run (no change). Round-3 peak over its 4 runs (439.7, 444.7, 445.7, 488.8): mean 454.7 vs 470.5, worst 488.8 vs 498.5. That still meets rule (a) numerically, but the run-to-run spread (about 50 to 60 MB) is larger than the effect, and the idle rule (b) is NOT met. Kept as shipped (rule (a)); the evidence for it is weak.
- New candidate, NOT adopted (it is code, not an ENV): import fastembed at startup in the main thread. Not tested on the shipped code path, only through the wrapper.

### C8.6 criteria re-run (2026-10-19, image with `EMBEDDING_THREADS=1`)
Setup: image CMD as shipped, `--memory=512m --memory-swap=512m --cpus=0.1`, `PDF_MAX_CONCURRENCY=1`, `PDF_TIMEOUT_SECONDS=120`, `APP_ENV=production`, local DB, **Groq stub (GROQ_API_KEY is not available to this session, so NOT real Groq)**, 10 rounds, each: login, then 5 chats and 1 unique 10-page PDF at once. PSS and cgroup anon sampled every 1 s, so shorter spikes (the 64 MB Argon2 transient) can be missed. Container log saved (`results/c86.log` in the scratchpad).

| Round | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| PSS peak (MB) | 388.9 | 438.7 | 439.7 | 440.2 | 485.4 | 485.4 | 485.6 | 485.7 | 485.9 | 485.8 |
| cgroup anon at that sample (MiB) | 339.4 | 387.5 | 388.4 | 389.0 | 434.2 | 434.2 | 370.3 | 434.4 | 434.5 | 434.5 |
| PDF upload, whole request (s) | 75.3 | 68.3 | 66.7 | 63.4 | 70.4 | 59.2 | 64.9 | 69.5 | 69.2 | 64.4 |

- Time to ready 61.8 s; idle PSS 323.5 MB; PSS 6 s after the last round 422.0 MB. Memory steps up at rounds 2 and 5 and is flat for rounds 5 to 10; 10 rounds cannot rule out slower growth.
- `memory.events`: `oom 0`, `oom_kill 0`, `max 31` (C7: 1017). `memory.stat` anon at the end: 388,788,224 bytes (370.8 MiB). Docker `OOMKilled=false`.
- Chat: 50 of 50 returned 200 with no error event (slowest per round 7.5 to 20.0 s, stub LLM). PDF: 10 of 10 returned 201, whole request 59.2 to 75.3 s (median 67.5). Extraction alone in the idle container (3 runs, `docker exec` of the worker): 9.6, 11.6, 13.4 s.
- Container log: no errors, tracebacks or 500s. The C7 500 on PDF upload did not recur (0 of 10) and its cause was never captured, so it is still unexplained.

Criteria (fixed in advance):
- **PSS peak at most 461 MB: FAIL.** Rounds 5 to 10 peaked at 485.4 to 485.9 MB; rounds 1 to 4 were 388.9 to 440.2.
- **oom_kill 0: PASS** (0; the limit was reached 31 times).
- **PDF upload succeeds at a wall timeout of 120 s or less: PASS** (10 of 10, slowest 75.3 s) for this stub-LLM, local-DB setup. Not shown with real Groq or over the WAN to the database.

Options when the criteria fail (listed, none chosen; measured numbers only):
- Import fastembed in the main thread at startup: idle -10.6 to -15.5 MB in 3 of 3 wrapper runs (C8.5c); peak effect not separable from noise; not tested on shipped code.
- Reduce the PDF step: it keeps +38.4 / +41.3 MB after one upload (C8.4), extraction child up to 27.6 MB; e.g. lower `pdf_memory_bytes`, fewer pages (`MAX_PDF_PAGES` is 200 today). Not measured.
- Fewer simultaneous logins or chats: Argon2 adds a 64 MB transient per hash (C8.4). Not measured as a lever.
- Model: warm-up is +229.5 to +230.2 MB of 321 MB PSS at ready (C8.4), 204.6 MB of it anonymous (C8.3b); the model file is 66.5 MB. A smaller or lazily loaded model changes this; not measured.
- Larger instance (C8.7): `0.5c-512mb` is also 512 MB ($7/month); `1c-2g` is 1 CPU, 2 GB, $25/month.
- Accept the free class: 10 of 10 rounds completed with `oom_kill 0` at a 485.9 MB PSS peak, but the 461 MB rule fails and C7 saw the container OOM-killed at PDF concurrency 2.

### C8.7 Render web instance types (read 2026-10-19)
RAM and CPU: https://render.com/docs/compute-plans (web service table). Price: https://render.com/pricing.md ("Services & Workers" table; the compute-plans page itself has no prices and says to see the pricing page; https://render.com/pricing returned no table and https://render.com/docs/pricing is a 404). Both pages were read through a page-to-text tool that summarises, so transcription was not checked against the live page by eye.

| Plan ID | CPU | RAM | Price |
|---|---|---|---|
| `free` | 0.1 CPU (pricing page says only "Free") | 512 MB | $0/month |
| `0.5c-512mb` (legacy `starter`) | 0.5 CPU | 512 MB | $7/month |
| `1c-2g` (legacy `standard`) | 1 CPU | 2 GB | $25/month |
| `2c-4g` (legacy `pro`) | 2 CPU | 4 GB | $85/month |
| `2c-8g` | 2 CPU | 8 GB | $135/month |
| `2c-16g` | 2 CPU | 16 GB | $200/month |
| `4c-8g` (legacy `pro_plus`) | 4 CPU | 8 GB | $175/month |
| `4c-16g` (legacy `pro_max`) | 4 CPU | 16 GB | $225/month |
| `4c-32g` | 4 CPU | 32 GB | $350/month |
| `8c-16g` | 8 CPU | 16 GB | $300/month |
| `8c-32g` (legacy `pro_ultra`) | 8 CPU | 32 GB | $450/month |
| `8c-64g` | 8 CPU | 64 GB | $1,000/month |
| `12c-24g` | 12 CPU | 24 GB | $450/month |
| `12c-48g` | 12 CPU | 48 GB | $800/month |
| `12c-96g` | 12 CPU | 96 GB | $1,500/month |

## Cloudflare-embedding plateau (recorded in the Gate 0 check of 2026-10-20, local Docker; Render NOT measured)
This is the only memory measurement with the production embedding provider. Source: `docs/cleanup/gate0.md`, item 7. The harness `bench.py` lived in a session scratchpad and is not in the repo, so the sampler details below are what the gate record states and nothing more.
- Method: image `helphub-backend:c9b`, local Docker, `--memory=512m --memory-swap=512m --cpus=0.1`; 10 rounds per run, each round 5 chats plus 1 10-page PDF upload; real Cloudflare Workers AI embeddings; **stub LLM (no Groq)**; local pgvector Postgres (no Supabase, no WAN latency to the database); 6 runs.
- Result: max PSS 165.2 to 165.5 MB; plateau 165.1 to 165.5 MB; 0 oom_kills; 360 of 360 requests ok (6 runs x 10 rounds x 6 requests).
- Likely reason it is far below the 321 to 485 MB of C7/C8: the ONNX model (about +230 MB at warm-up, C8.4) is not loaded when embeddings are remote. This was not verified by a measurement. The two sets of numbers are different configurations; do not mix them.
- Not measured: Render (CPU and memory behaviour of the real free instance, startup time, wake from sleep), Supabase over the WAN, real Groq streaming, Cloudflare latency or quota behaviour under load (AR-20), concurrency above one PDF, PDFs over 10 pages. The plateau definition and sampling interval are not recorded in the repo.
- Consequence: the C7 criteria failure (PSS above 461 MB) applies to the local-model image only. No criterion has been checked against Render.

## Open items
- [ ] **Render IPv6 to Supabase direct connection: unknown.** Not testable from the dev box. Stay on the session pooler until answered; test on the first Render deploy and record the result here.
- [x] **`MIGRATION_DATABASE_URL` is optional for the app** (C8): leave it unset on the runtime service; set it only where `alembic upgrade head` runs. Never put the owner URL on the runtime service.
- [ ] **Client IPs behind Render's proxy** are not trusted (uvicorn runs without `--proxy-headers`), which is why login limits are per account, not per IP (AR-19).
- [ ] **Live smoke script**: built (`backend/scripts/smoke_live.py`); not yet run against the deployed URL.
- [ ] **Uptime bot** and the keep-alive target (`GET /health/ready`): not configured. When it is: set it to alert only after 2 consecutive failures (tolerate one). C7 saw one `/health/ready` timeout under load at 0.1 CPU (the 5 s `SELECT 1` limit), so a single failed probe is expected noise, not an outage.
- [ ] **Render's health check path must be `/health`** (liveness, touches nothing else), not `/health/ready`. Reason: a database blip or a slow `SELECT 1` on a busy 0.1 CPU instance would otherwise count against the instance, and Render restarts an instance after 60 s of failed checks (https://render.com/docs/health-checks, quoted in the table above). `/health/ready` is for the uptime bot and the Supabase keep-alive only.
- [ ] **Memory gate (Gate 0 item 7) is OPEN**: the C7 criteria failed for the local-model image; the Cloudflare-embedding image plateaus at about 165 MB locally (section above), but Render is unmeasured. No instance class or architecture change has been made.
