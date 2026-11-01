# Deploy runbook (Render + Supabase)

## Status
Lines marked owner-reported come from the owner and have not been checked against GitHub, Render, Vercel, Supabase or the uptime service.
- Supabase is at migration 0012. The demo tenant, a viewer user and 24 documents were seeded on 2026-10-24 (owner-reported).
- The Render service is live, the Vercel project is deployed and the uptime bot is set up (owner-reported; the bot's service, interval and alert rule are not recorded here). `backend/scripts/smoke_live.py` passed against the Render service on 2026-10-29.
- `.github/workflows/db-ops.yml` has two manual jobs, `migrate` and `backup`. **No backups exist: the `backup` job refuses to run while the repository is public.** There is no `render.yaml`.
- **Render itself is not measured.** No memory, region or cold-start figure from Render is recorded. The one memory measurement with the production embedding provider is under "Cloudflare-embedding plateau" below.
- Older measurements of the local fastembed model (container, load and memory tests) were removed from this file; they are in git history at commit `1bee6c6`.

## Connection defaults
- The app (`DATABASE_URL`) and migrations (`MIGRATION_DATABASE_URL`) both use the Supabase **session pooler**, port 5432, user `role.<project-ref>`. It works with no asyncpg changes.
- On the transaction pooler (port 6543) set asyncpg `statement_cache_size=0` in `app/db/session.py`; without it 174 of 180 test transactions failed with SQLSTATE 26000.
- The Supabase dashboard shows `postgresql://...`. Add `+asyncpg` (`postgresql+asyncpg://...`) before pasting, because the app refuses to start with any other prefix.
- Run migrations only as `helphub_owner`, never as `postgres` (otherwise Supabase grants its API roles access to new tables).

## Supabase role setup (once, as `postgres` over the session pooler)
`postgres` is not a superuser (it has CREATEROLE and BYPASSRLS).
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
pgvector must live in schema `public`. Create it as `postgres` with `create extension vector with schema public`. The dashboard toggle installs it in schema `extensions`, where `helphub_owner` and `helphub_app` cannot see the type (their search_path is `"$user", public`), and `helphub_owner` cannot create it itself because the extension is not trusted. Migration 0001's `CREATE EXTENSION IF NOT EXISTS vector` does nothing once it exists.

Run migrations from a copy of the tracked files with no `.env` (`git archive HEAD backend | tar -x -C <dir>`), with `MIGRATION_DATABASE_URL` and the other settings in the shell environment, because `alembic/env.py` loads the app settings, which read `.env` if there is one.

Do not rotate a role's password repeatedly through the pooler: it kept rejecting the new password, and the repeated failures tripped its circuit breaker (`ECIRCUITBREAKER`), which blocked all new connections for minutes.

### Supabase turns on RLS for every new table (seen 2026-10-20)
An event trigger `ensure_rls` calls `rls_auto_enable` after every DDL command, so every new table gets `ENABLE ROW LEVEL SECURITY` with no policy, including `alembic_version`, `tenants` and `users` (checked by a query the owner ran on Supabase). A local Postgres has no such trigger. The body of `rls_auto_enable` has not been read, so do not assume it does anything else.

Before migration 0011, `tenants` had RLS on and no policy, so `helphub_app` was denied (`new row violates row-level security policy for table "tenants"`) and `scripts/seed_tenant.py` failed with nothing written. Locally RLS was off and the owner is a superuser, so the same code passed.

Fix: migration `0011_tenants_rls.py` enables RLS on `tenants` with explicit `helphub_app` policies for SELECT and INSERT only (no UPDATE, DELETE or FORCE). `tests/migrations/test_rls_invariant.py` requires RLS and at least one policy on every table in `public` except `alembic_version`. Because there is no FORCE, the table owner bypasses RLS, so the runtime service must never get `MIGRATION_DATABASE_URL` (AR-21).

## Render environment (free class, 512 MB, 0.1 CPU)
All plain environment variables read by `app/core/config.py`. Render sets `PORT` (default 10000) and the image binds `0.0.0.0:$PORT`.

| Variable | Value | Note |
|---|---|---|
| `APP_ENV` | `production` | hides `/docs`, `/redoc`, `/openapi.json`; startup fails without `GROQ_API_KEY` or with `CORS_ORIGINS=*` |
| `DATABASE_URL` | `postgresql+asyncpg://helphub_app.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres?ssl=require` | session pooler, app role |
| `MIGRATION_DATABASE_URL` | not set on the runtime service | only Alembic and the test fixtures read it (it raises if read while unset) |
| `JWT_SECRET` | 32+ random characters | rejected if it is the `.env.example` placeholder |
| `GROQ_API_KEY` | secret | required when `APP_ENV=production` |
| `CORS_ORIGINS` | frontend origin(s), comma-separated | empty means no CORS headers |
| `ALLOW_PUBLIC_REGISTRATION` | `false` (default) | stays `false` for the closed beta; tenants are created with `scripts/seed_tenant.py` |
| `PDF_TIMEOUT_SECONDS` | `120` | raised from 10 because a 10-page PDF took longer than 10 s at 0.1 CPU in 2 of 2 local runs; 120 is a starting value |
| `PDF_CPU_SECONDS` | unset (stays 10) | CPU time, not wall time; a kernel `RLIMIT_CPU` backstop |
| `PDF_MAX_CONCURRENCY` | `1` | a second concurrent upload waits `PDF_QUEUE_WAIT_SECONDS` (5 s), then gets 503 |
| `READY_TIMEOUT_SECONDS` | unset (stays 5) | how long `/health/ready` waits for `SELECT 1` before answering 503; raise only if readiness flaps under load |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | `15` / `7` (defaults) | |
| `RATE_LIMIT_*` | defaults | login 5 per account and 30 global per 60 s; search 60 and chat 10 per user per 60 s; in-process (AR-13, AR-19) |

## Creating tenants (registration is closed)
From `backend/`, with `DATABASE_URL` (app role, session pooler), `MIGRATION_DATABASE_URL` and `JWT_SECRET` set in the shell:
`SEED_ADMIN_PASSWORD=... uv run python scripts/seed_tenant.py --name "Acme" --slug acme --email admin@acme.test`
(leave out the variable to be prompted for the password). `scripts/` is not in the image; run it from a checkout.

**Stale shell variables win.** An exported `DATABASE_URL`, `JWT_SECRET` or `MIGRATION_DATABASE_URL` from an earlier shell overrides the env file and `backend/.env`. Re-export the values you mean, or open a fresh shell, before running the script, so it cannot hit the wrong database.

## Onboarding a closed-beta workspace
Registration is closed (there is no `/register` page).
1. A request arrives by email from the home page's "Request access" link: workspace name, slug and admin email. It must never contain a password; if one is sent, treat it as exposed.
2. Check the slug uses only lowercase letters, digits and hyphens and is not taken, then create the tenant and its admin with `scripts/seed_tenant.py` as above.
3. Send the slug, admin email and initial password to the requester outside email (a channel they already use with you, not the request thread).
4. The admin signs in and adds the rest of the team at `/users` (roles admin, agent, viewer; the page can generate a password, shown once). Share those passwords outside email too.
5. There is no password reset or deactivate endpoint yet (decisions.md D17): a forgotten password means creating a new user with a different email, and a user cannot be removed from the UI.

## Seeding the hosted demo tenant
Prerequisite: the hosted tenant and its admin exist (see "Creating tenants"). Use a separate terminal opened only for this job, and run from `backend/`.

**How it works.** `scripts/create_viewer.py` and `scripts/load_demo_corpus.py` are plain HTTP clients (httpx). They log in with `POST /auth/login`, then call `POST /users` (create_viewer) or `GET /documents`, `POST /documents/upload`, `GET /documents/{id}` (load_demo_corpus). They never touch the database. The corpus needs a locally running app started with the hosted `DATABASE_URL`, which embeds the uploads and writes to the hosted database. The viewer alone can be created through the hosted API instead (see "Creating the viewer through the hosted API"). Pointing `load_demo_corpus.py` at Render would run the embedding on the 0.1 CPU instance; that is not covered here.

**Stale shell variables.** Exported `DATABASE_URL`, `JWT_SECRET`, `MIGRATION_DATABASE_URL`, `BASE_URL`, `TENANT_SLUG`, `EMAIL` or `PASSWORD` from an earlier shell override the env file and `backend/.env`. The steps below start by unsetting them, but a fresh terminal is safest. If a value is not what you expect, stop: step 3 shows where the database variables point.

| Variable | Used by | Source |
|---|---|---|
| `DATABASE_URL` (app role, `helphub_app`) | the local app | `~/.helphub-supabase.env` |
| `JWT_SECRET` | the local app | `~/.helphub-supabase.env` |
| `BASE_URL` (`http://127.0.0.1:8001`), `TENANT_SLUG`, `EMAIL`, `PASSWORD` (hosted tenant admin) | both scripts | `~/.helphub-hosted-creds` (below) |
| `BASE_URL`, `SMOKE_TENANT_SLUG`, `SMOKE_EMAIL`, `SMOKE_PASSWORD` | `scripts/smoke_live.py` only (it does not read `TENANT_SLUG`, `EMAIL`, `PASSWORD` or the creds-file fallback) | map them from the hosted creds file, see "Live smoke test" |
| `VIEWER_EMAIL`, `VIEWER_PASSWORD` | create_viewer only | typed into the shell. The email must differ from the admin's `EMAIL`; the password must be 12 to 128 characters |

`MIGRATION_DATABASE_URL` is never exported for this job; the app does not need it at runtime.

**Credentials files.** `~/.helphub-local-creds` is the LOCAL database's admin and is never used here. The scripts fall back to it for any of `BASE_URL`, `TENANT_SLUG`, `EMAIL`, `PASSWORD` that is not set, so this terminal exports all four from `~/.helphub-hosted-creds` (mode 600, `KEY=VALUE` lines, the same four keys) and the fallback is never reached. Create that file yourself; no script writes it. `~/.helphub-supabase.env` must hold `JWT_SECRET` and a `DATABASE_URL=` line (the app-role session-pooler URL, `postgresql+asyncpg://...`); the export step fails without them.

**About `.env`.** The app still reads `backend/.env` for settings the shell does not set. Exported variables win, so `DATABASE_URL` and `JWT_SECRET` come from the shell. Do not edit `.env` for this job.

```bash
cd ~/projects/helphub/backend

# 0. Drop anything left over from an earlier shell. A fresh terminal is safer still.
#    (exit 1 in the checks below closes this throwaway terminal on purpose.)
unset DATABASE_URL JWT_SECRET MIGRATION_DATABASE_URL BASE_URL TENANT_SLUG EMAIL PASSWORD VIEWER_EMAIL VIEWER_PASSWORD

# 1. Export only DATABASE_URL and JWT_SECRET (nothing else from the file).
for k in DATABASE_URL JWT_SECRET; do
  v=$(grep -E "^(export +)?$k=" ~/.helphub-supabase.env | tail -1 \
      | sed -E "s/^(export +)?$k=//; s/^['\"]//; s/['\"]$//")
  [ -n "$v" ] || { echo "missing $k in ~/.helphub-supabase.env"; exit 1; }
  export "$k=$v"
done
unset v

# 2. Hosted tenant admin (all four keys, so ~/.helphub-local-creds is not used).
for k in BASE_URL TENANT_SLUG EMAIL PASSWORD; do
  v=$(grep -E "^$k=" ~/.helphub-hosted-creds | tail -1 \
      | sed -E "s/^$k=//; s/^['\"]//; s/['\"]$//")
  [ -n "$v" ] || { echo "missing $k in ~/.helphub-hosted-creds"; exit 1; }
  export "$k=$v"
done
unset v
case "$BASE_URL" in http://127.0.0.1:8001|http://localhost:8001) ;; *) echo "BASE_URL must be the local app on :8001"; exit 1 ;; esac

# 3. Check where the database variables point. Expected in THIS terminal only:
#    DATABASE_URL (environment): hosted; MIGRATION_DATABASE_URL (environment): unset;
#    the two ".env only" lines: local. Exit code 1 is expected. In any other terminal
#    a "hosted" result is a stop sign.
uv run python scripts/check_local_db.py

# 4. Start the app on a port (no reload) and wait until it is ready.
uv run fastapi run app/main.py --host 127.0.0.1 --port 8001 &
APP_PID=$!
ready=0
for _ in $(seq 1 90); do                      # at most 90 x 2 s = 180 s
  if curl -fsS http://127.0.0.1:8001/health/ready >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
[ "$ready" = 1 ] || { echo "app not ready after 180 s; stopping"; kill "$APP_PID"; exit 1; }

# 5. Viewer, then corpus. Both are idempotent (existing viewer / existing titles are skipped).
read -r -p "viewer email: " VIEWER_EMAIL; read -r -s -p "viewer password: " VIEWER_PASSWORD; echo
export VIEWER_EMAIL VIEWER_PASSWORD
uv run python scripts/create_viewer.py       # prints created=N existing=N conflicts=N
uv run python scripts/load_demo_corpus.py    # prints files= uploaded= skipped= failed= not_ready=
```

**Viewer password rule.** `POST /users` takes `UserCreate` (`backend/app/schemas/user.py`, `password: NewPassword`), and `NewPassword` is a string of **12 to 128 characters** (`backend/app/schemas/types.py`). The schema has no other rule (no digit or symbol requirement); this was checked in the schema only, not in every service. `create_viewer.py` does not check the length itself: a shorter password makes the API reject it, and the script prints `create failed: HTTP <status>` and exits 1. The script and the schema lowercase the email.

Expect `conflicts=0`, `failed=0` and `not_ready=0`. Exit 0 from both scripts means success; a rerun should show `created=0 existing=1` and `uploaded=0 skipped=<files>`.

### Creating the viewer through the hosted API
`create_viewer.py` only needs an HTTP endpoint, so it can run against the Render service with no local app and no `DATABASE_URL` or `JWT_SECRET`. Use a fresh terminal and keep the hosted admin credentials in `~/.helphub-hosted-creds`, with `BASE_URL` set to the Render URL (`https://<service>.onrender.com`; the real URL is not recorded in the repo).

**The viewer email must differ from the admin's `EMAIL`.** If the email already belongs to a user who is not a viewer, the script reports `conflicts=1` and exits 1 without creating anything.

```bash
cd ~/projects/helphub/backend
unset DATABASE_URL JWT_SECRET MIGRATION_DATABASE_URL BASE_URL TENANT_SLUG EMAIL PASSWORD VIEWER_EMAIL VIEWER_PASSWORD

for k in BASE_URL TENANT_SLUG EMAIL PASSWORD; do
  v=$(grep -E "^$k=" ~/.helphub-hosted-creds | tail -1 \
      | sed -E "s/^$k=//; s/^['\"]//; s/['\"]$//")
  [ -n "$v" ] || { echo "missing $k in ~/.helphub-hosted-creds"; exit 1; }
  export "$k=$v"
done
unset v
case "$BASE_URL" in *'<'*|*'>'*) echo "BASE_URL still contains a placeholder"; exit 1 ;; https://*.onrender.com) ;; *) echo "BASE_URL is not the Render URL"; exit 1 ;; esac

# Free-tier cold start is about a minute (Render's figure). Wake it first, bounded.
ready=0
for _ in $(seq 1 30); do                      # at most 30 x 5 s = 150 s
  if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 5
done
[ "$ready" = 1 ] || { echo "service not up after 150 s; stopping"; exit 1; }

read -r -p "viewer email (not the admin's): " VIEWER_EMAIL
[ "$VIEWER_EMAIL" != "$EMAIL" ] || { echo "viewer email must differ from the admin email"; exit 1; }
read -r -s -p "viewer password (12-128 chars): " VIEWER_PASSWORD; echo
export VIEWER_EMAIL VIEWER_PASSWORD
uv run python scripts/create_viewer.py        # created=1 existing=0 conflicts=0; a rerun: created=0 existing=1
unset BASE_URL TENANT_SLUG EMAIL PASSWORD VIEWER_EMAIL VIEWER_PASSWORD
```
Login is limited to 5 attempts per 60 s per account (AR-19), so do not loop the script. These scripts were run on 2026-10-24 against the hosted Supabase database through a local app on :8001 (owner-reported); they have not been run against the Render service.

**Live smoke test.** `scripts/smoke_live.py` reads `BASE_URL`, `SMOKE_TENANT_SLUG`, `SMOKE_EMAIL` and `SMOKE_PASSWORD`, so map the hosted creds file onto them in a subshell (nothing stays exported; `BASE_URL` must be the Render URL, not a local one). It makes real changes: it uploads a document, then deletes it.

```bash
( set -a; . ~/.helphub-hosted-creds; set +a
  BASE_URL="https://<service>.onrender.com" \
  SMOKE_TENANT_SLUG="$TENANT_SLUG" SMOKE_EMAIL="$EMAIL" SMOKE_PASSWORD="$PASSWORD" \
  uv run python scripts/smoke_live.py )
echo "exit=$?"
```
Expected: one line per step (login, upload, wait_ready, search, chat_stream, delete, logout) and `SMOKE OK`. It passed on 2026-10-29 and again on 2026-10-31.

**Closing the terminal.** Never run `pytest`, `scripts/gate.sh` or `scripts/flake_hunt.sh` in this terminal: this shell holds the hosted `DATABASE_URL`. When done:

```bash
kill "$APP_PID"; wait "$APP_PID" 2>/dev/null
ss -ltn 'sport = :8001'        # must list nothing
unset DATABASE_URL JWT_SECRET BASE_URL TENANT_SLUG EMAIL PASSWORD VIEWER_EMAIL VIEWER_PASSWORD APP_PID
exit                           # close the terminal; do not reuse it
```

## Migrations
Run `uv run alembic upgrade head` with `MIGRATION_DATABASE_URL` = `helphub_owner.<ref>` over the session pooler, from a dev machine or a CI job; never as `postgres` and never as the app's runtime role. `.github/workflows/ci.yml` only runs tests. A manual `migrate` job exists in `.github/workflows/db-ops.yml` (workflow_dispatch, environment `production`, secret `MIGRATION_DATABASE_URL`). A deploy does not trigger it, and whether it has been run is not recorded here.

## Facts about the free tiers
- Render's free tier has no pre-deploy command, so migrations run from CI or a dev machine (https://render.com/docs/deploys).
- A service has 15 minutes to bind its port and pass health checks after a start; if it fails, Render cancels the deploy and keeps the old instance (https://render.com/docs/health-checks). Our start took 40 to 56 s on a dev box, so warm-up stays blocking. Not known: whether the "60 s of failed health checks restarts the instance" rule also applies while the instance is still starting; watch the first deploy.
- Wake-up from sleep "takes about one minute" (Render's figure, https://render.com/docs/free). Not measured on Render.
- Render free RAM is 512 MB.
- UptimeRobot's free plan checks every 5 minutes (50 monitors), under Render's 15-minute spin-down (https://uptimerobot.com/pricing.md). Its free-plan terms for a non-personal project were not checked.
- Supabase pauses free projects after 1 week of inactivity (https://supabase.com/pricing, https://supabase.com/docs/guides/platform/free-project-pausing). Whether `SELECT 1` from `/health/ready` counts as activity is not known (the docs do not define "user database activity"); a scheduled job doing a real table read would be a cheap hedge.
- Backups: Supabase free has none, and the `backup` job in `db-ops.yml` refuses to run while the repository is public (see Status).

## Cloudflare-embedding plateau (local Docker, 2026-10-20; Render NOT measured)
The only memory measurement with the production embedding provider. The test script lived in a session scratch folder and is not in the repo, and the original record was removed (see commit `1bee6c6`), so only what is below is known.
- Setup: local Docker with `--memory=512m --memory-swap=512m --cpus=0.1`; 6 runs of 10 rounds, each round 5 chats plus one 10-page PDF upload; real Cloudflare Workers AI embeddings, a **stub LLM (no Groq)**, a local pgvector Postgres (no Supabase, no network delay to the database).
- Result: max PSS 165.2 to 165.5 MB; plateau 165.1 to 165.5 MB; no out-of-memory kills; 360 of 360 requests ok.
- Probably far below the 321 to 485 MB measured earlier with the local model because the ONNX model (about +230 MB at warm-up) is not loaded when embeddings are remote. That was not measured, and the two sets of numbers are different setups.
- Not measured: Render (CPU and memory of the real free instance, startup time, wake from sleep), Supabase over the internet, real Groq streaming, Cloudflare latency or quota behaviour under load (AR-20), more than one PDF at a time, PDFs over 10 pages. The plateau definition and sampling interval are not recorded.
- The earlier memory-criteria failure (PSS above 461 MB) applies to the local-model image only. No criterion has been checked against Render.

## Open items
- [ ] **Render IPv6 to Supabase direct connection: unknown.** Not testable from the dev box. Stay on the session pooler; test on the first Render deploy and record the result here.
- [x] **`MIGRATION_DATABASE_URL` is optional for the app:** leave it unset on the runtime service and set it only where `alembic upgrade head` runs. Never put the owner URL on the runtime service.
- [ ] **Client IPs behind Render's proxy** are not trusted (uvicorn runs without `--proxy-headers`), which is why login limits are per account, not per IP (AR-19).
- [x] **Live smoke script:** `backend/scripts/smoke_live.py` passed against the deployed Render service (owner-reported 2026-10-26; run again 2026-10-29 and 2026-10-31).
- [x] **Uptime bot** and keep-alive target (`GET /health/ready`): set up (owner-reported 2026-10-26; whether it follows the rule below is not checked). Alert only after 2 consecutive failures. An earlier local load test at 0.1 CPU saw one `/health/ready` timeout (the 5 s `SELECT 1` limit), so one failed probe is expected noise.
- [ ] **Render's health check path must be `/health`** (liveness only), not `/health/ready`. A database blip or a slow `SELECT 1` on a busy 0.1 CPU instance would otherwise count against the instance, and Render restarts an instance after 60 s of failed checks. `/health/ready` is for the uptime bot and the Supabase keep-alive only.
- [ ] **Memory check is still open:** the earlier criteria failed for the local-model image; the Cloudflare-embedding image plateaus at about 165 MB locally, but Render is not measured. No instance class or architecture change has been made.
