# Deploy runbook (Render + Supabase)

## Status
Lines marked owner-reported were stated by the owner and not checked against GitHub, Render, Vercel, Supabase or the uptime service.
- Supabase is at migration 0012; the demo tenant, a viewer user and 24 documents were seeded on 2026-10-24 (owner-reported).
- The Render service is live, the Vercel project is deployed and the uptime bot is configured (owner-reported; the bot's service, interval and alert rule are not recorded here). `backend/scripts/smoke_live.py` passed against the Render service on 2026-10-29 (all steps ok).
- `.github/workflows/db-ops.yml` has two manual jobs, `migrate` and `backup`. **No backups exist: the `backup` job refuses to run while the repository is public.** `render.yaml` does not exist.
- **Render itself is unmeasured.** No Render memory, region or cold-start figure is recorded. The only memory measurement with the production embedding provider (Cloudflare, AR-20) is in "Cloudflare-embedding plateau" below.
- Older measurements of the local fastembed model (container, load and memory tests) were removed from this file; they are in git history at tag `pre-prune`.

## Connection defaults
- Both the app (`DATABASE_URL`) and migrations (`MIGRATION_DATABASE_URL`) use the Supabase **session pooler**, port 5432, username `role.<project-ref>`. Measured working with no asyncpg changes.
- If the app is ever moved to the transaction pooler (port 6543), set asyncpg `statement_cache_size=0` in `app/db/session.py`; without it 174 of 180 test transactions failed with SQLSTATE 26000.
- The Supabase dashboard shows `postgresql://...`; add `+asyncpg` (`postgresql+asyncpg://...`) before pasting it, because the app refuses to start with any other prefix.
- Migrations run only as `helphub_owner`, never as `postgres` (otherwise Supabase grants the API roles access to new tables).

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

## Render environment (free class, 512 MB, 0.1 CPU)
All of these are plain environment variables read by `app/core/config.py` (no code change). Render sets `PORT` (default 10000); the image binds `0.0.0.0:$PORT`.

| Variable | Value | Note |
|---|---|---|
| `APP_ENV` | `production` | hides `/docs`, `/redoc`, `/openapi.json`; startup fails without `GROQ_API_KEY` or with `CORS_ORIGINS=*` |
| `DATABASE_URL` | `postgresql+asyncpg://helphub_app.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres?ssl=require` | session pooler, app role |
| `MIGRATION_DATABASE_URL` | not set on the runtime service | optional for the app; read only by alembic and the test fixtures (raises if read while unset) |
| `JWT_SECRET` | 32+ random characters | rejected if it is the `.env.example` placeholder |
| `GROQ_API_KEY` | secret | required when `APP_ENV=production` |
| `CORS_ORIGINS` | frontend origin(s), comma-separated | empty = no CORS headers |
| `ALLOW_PUBLIC_REGISTRATION` | `false` (default) | stays `false` for the closed beta; tenants are created with `scripts/seed_tenant.py` |
| `PDF_TIMEOUT_SECONDS` | `120` | raised from 10: at 0.1 CPU a 10-page PDF exceeded 10 s in 2 of 2 local runs; 120 is the starting value |
| `PDF_CPU_SECONDS` | unset (stays 10) | CPU time, not wall time; kernel `RLIMIT_CPU` backstop |
| `PDF_MAX_CONCURRENCY` | `1` | a second concurrent upload waits `PDF_QUEUE_WAIT_SECONDS` (5 s) and then gets 503 |
| `READY_TIMEOUT_SECONDS` | unset (stays 5) | how long `/health/ready` waits for `SELECT 1` before 503; raise it only if readiness flaps under load |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | `15` / `7` (defaults) | |
| `RATE_LIMIT_*` | defaults | login 5 per account and 30 global per 60 s; search 60 and chat 10 per user per 60 s; in-process (AR-13, AR-19) |

## Creating tenants (registration is closed)
From `backend/`, with `DATABASE_URL` (app role, session pooler), `MIGRATION_DATABASE_URL` and `JWT_SECRET` set in the shell:
`SEED_ADMIN_PASSWORD=... uv run python scripts/seed_tenant.py --name "Acme" --slug acme --email admin@acme.test`
(omit the variable to be prompted). `scripts/` is not in the image; run it from a checkout.

**Stale shell variables win.** An exported `DATABASE_URL`, `JWT_SECRET` or `MIGRATION_DATABASE_URL` left over from an earlier shell overrides the env file and `backend/.env` (exported variables take precedence). Re-export the values you mean, or open a fresh shell, before running this script, so it cannot hit the wrong database.

## Onboarding a closed-beta workspace
Registration is closed (no `/register` page). Steps:
1. A request arrives by email from the home page's "Request access" link: workspace name, workspace slug and admin email. It must never contain a password; if one is sent, treat it as exposed.
2. Check the slug is lowercase letters, digits and hyphens and is not taken, then create the tenant and its admin with `scripts/seed_tenant.py` as in "Creating tenants" above.
3. Send the workspace slug, admin email and initial password to the requester outside email (a channel they already use with you; not the request thread).
4. The admin signs in and adds the rest of the team at `/users` (roles admin, agent, viewer; the page can generate a password, shown once). Those passwords are also shared outside email.
5. There is no password reset or deactivate endpoint yet (decisions.md D17): a forgotten password means creating a new user with a different email, and a user cannot be removed from the UI.

## Seeding the hosted demo tenant
Prerequisite: the hosted tenant and its admin already exist (see "Creating tenants"). Run this in a SEPARATE terminal opened only for this job, from `backend/`.

**How it works.** `scripts/create_viewer.py` and `scripts/load_demo_corpus.py` are plain HTTP clients (httpx). They log in with `POST /auth/login` and then call `POST /users` (create_viewer) or `GET /documents`, `POST /documents/upload`, `GET /documents/{id}` (load_demo_corpus). They never touch the database. So a locally running app, started with the hosted `DATABASE_URL`, is required for the corpus: the app embeds the uploads and writes to the hosted database. The viewer alone can instead be created through the hosted API: see "Creating the viewer through the hosted API" below. (Pointing `load_demo_corpus.py` at Render too would run embedding on the 0.1 CPU instance; not covered here.)

**Stale shell variables.** Exported `DATABASE_URL` / `JWT_SECRET` (and `MIGRATION_DATABASE_URL`, `BASE_URL`, `TENANT_SLUG`, `EMAIL`, `PASSWORD`) from an earlier shell override the env file and `backend/.env`. The steps below start by unsetting them and re-exporting from the files, but the safest course is a fresh terminal. If a value is not what you expect, stop: step 3 shows where the database variables point.

| Variable | Used by | Source |
|---|---|---|
| `DATABASE_URL` (app role, `helphub_app`) | the local app | `~/.helphub-supabase.env` |
| `JWT_SECRET` | the local app | `~/.helphub-supabase.env` |
| `BASE_URL` (`http://127.0.0.1:8001`), `TENANT_SLUG`, `EMAIL`, `PASSWORD` (hosted tenant admin) | both scripts | `~/.helphub-hosted-creds` (below) |
| `BASE_URL`, `SMOKE_TENANT_SLUG`, `SMOKE_EMAIL`, `SMOKE_PASSWORD` | `scripts/smoke_live.py` only (it does NOT read `TENANT_SLUG`, `EMAIL`, `PASSWORD` or the creds-file fallback) | map them from the hosted creds file, see "Live smoke test" below |
| `VIEWER_EMAIL`, `VIEWER_PASSWORD` | create_viewer only | typed into the shell, environment only. The email must differ from the admin's `EMAIL`. The password must be 12 to 128 characters (below) |

`MIGRATION_DATABASE_URL` is never exported here. The app does not need it at runtime.

**Credentials files.** `~/.helphub-local-creds` is the LOCAL database's admin and is never used here. The scripts read it as a fallback for any of `BASE_URL`, `TENANT_SLUG`, `EMAIL`, `PASSWORD` that is not in the environment, so this terminal exports all four from `~/.helphub-hosted-creds` (mode 600, `KEY=VALUE` lines, same four keys) and the fallback is never reached. Create it yourself; no script writes it. As of 2026-10-24 `~/.helphub-supabase.env` holds only `JWT_SECRET`: add a `DATABASE_URL=` line (the app-role session-pooler URL, `postgresql+asyncpg://...`) before the steps below, or the export step fails.

**Caveat on `.env`.** The app still reads `backend/.env` for settings the shell does not set. Exported variables take precedence, so `DATABASE_URL` and `JWT_SECRET` come from the shell. Do not edit `.env` for this job.

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

**Viewer password rule.** `POST /users` takes `UserCreate` (`backend/app/schemas/user.py:14`, `password: NewPassword`), and `NewPassword` is a string of **12 to 128 characters** (`backend/app/schemas/types.py:13`, `min_length=12, max_length=128`). That schema has no other rule (no digit or symbol requirement); this was checked in the schema only, not in every service. `create_viewer.py` does not pre-check the length: a shorter password makes the API reject the request and the script prints `create failed: HTTP <status>` and exits 1 (`backend/scripts/create_viewer.py`). The email is lowercased by the script and the schema.

Expect `conflicts=0` and `failed=0 not_ready=0`. Exit 0 from both scripts means success; a rerun should show `created=0 existing=1` and `uploaded=0 skipped=<files>`.

### Creating the viewer through the hosted API
`create_viewer.py` only needs an HTTP endpoint, so it can run against the Render service with no local app and no `DATABASE_URL` / `JWT_SECRET`. Use a fresh terminal (stale-variable warning above) and keep the hosted admin credentials in `~/.helphub-hosted-creds`, with `BASE_URL` set to the Render URL (`https://<service>.onrender.com`; the real URL is not recorded in the repo).

**The viewer email must differ from the admin's `EMAIL`.** If the email already belongs to a user whose role is not `viewer`, the script reports `conflicts=1` and exits 1 without creating anything (`find_role` in `create_viewer.py`).

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
Login is rate limited per account (5 per 60 s, AR-19), so do not loop the script. These scripts were run on 2026-10-24 against the hosted Supabase database through a local app on :8001 (owner-reported); they have not been run against the Render service.

**Live smoke test.** `scripts/smoke_live.py` reads `BASE_URL`, `SMOKE_TENANT_SLUG`, `SMOKE_EMAIL` and `SMOKE_PASSWORD`, so map the hosted creds file onto them in a subshell (nothing stays exported; `BASE_URL` must be the Render URL, not a local one). It does real writes: it uploads a document, then deletes it.

```bash
( set -a; . ~/.helphub-hosted-creds; set +a
  BASE_URL="https://<service>.onrender.com" \
  SMOKE_TENANT_SLUG="$TENANT_SLUG" SMOKE_EMAIL="$EMAIL" SMOKE_PASSWORD="$PASSWORD" \
  uv run python scripts/smoke_live.py )
echo "exit=$?"
```
Expected: one line per step (login, upload, wait_ready, search, chat_stream, delete, logout) and `SMOKE OK`. Run 2026-10-29: all steps ok, exit 0.

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
| Render free RAM | **VERIFIED 512 MB** | |
| Backups | **GAP, not built**: Supabase free has none, and the `db-ops.yml` `backup` job refuses to run while the repository is public | see Status |

## Cloudflare-embedding plateau (recorded in the Gate 0 check of 2026-10-20, local Docker; Render NOT measured)
This is the only memory measurement with the production embedding provider. Source: the Gate 0 check of 2026-10-20 (the record was removed; see tag `pre-prune`). The harness `bench.py` lived in a session scratchpad and is not in the repo, so the sampler details below are what the gate record states and nothing more.
- Method: image `helphub-backend:c9b`, local Docker, `--memory=512m --memory-swap=512m --cpus=0.1`; 10 rounds per run, each round 5 chats plus 1 10-page PDF upload; real Cloudflare Workers AI embeddings; **stub LLM (no Groq)**; local pgvector Postgres (no Supabase, no WAN latency to the database); 6 runs.
- Result: max PSS 165.2 to 165.5 MB; plateau 165.1 to 165.5 MB; 0 oom_kills; 360 of 360 requests ok (6 runs x 10 rounds x 6 requests).
- Likely reason it is far below the 321 to 485 MB measured earlier with the local model: the ONNX model (about +230 MB at warm-up) is not loaded when embeddings are remote. This was not verified by a measurement. The two sets of numbers are different configurations; do not mix them.
- Not measured: Render (CPU and memory behaviour of the real free instance, startup time, wake from sleep), Supabase over the WAN, real Groq streaming, Cloudflare latency or quota behaviour under load (AR-20), concurrency above one PDF, PDFs over 10 pages. The plateau definition and sampling interval are not recorded in the repo.
- Consequence: the earlier memory-criteria failure (PSS above 461 MB) applies to the local-model image only. No criterion has been checked against Render.

## Open items
- [ ] **Render IPv6 to Supabase direct connection: unknown.** Not testable from the dev box. Stay on the session pooler until answered; test on the first Render deploy and record the result here.
- [x] **`MIGRATION_DATABASE_URL` is optional for the app** (measured earlier): leave it unset on the runtime service; set it only where `alembic upgrade head` runs. Never put the owner URL on the runtime service.
- [ ] **Client IPs behind Render's proxy** are not trusted (uvicorn runs without `--proxy-headers`), which is why login limits are per account, not per IP (AR-19).
- [x] **Live smoke script**: built (`backend/scripts/smoke_live.py`); passed twice against the deployed Render service (owner-reported 2026-10-26; output not recorded in the repo).
- [x] **Uptime bot** and the keep-alive target (`GET /health/ready`): configured (owner-reported 2026-10-26; whether it follows the rule below is not checked). It should be set to alert only after 2 consecutive failures (tolerate one). An earlier local load test at 0.1 CPU saw one `/health/ready` timeout (the 5 s `SELECT 1` limit), so a single failed probe is expected noise, not an outage.
- [ ] **Render's health check path must be `/health`** (liveness, touches nothing else), not `/health/ready`. Reason: a database blip or a slow `SELECT 1` on a busy 0.1 CPU instance would otherwise count against the instance, and Render restarts an instance after 60 s of failed checks (https://render.com/docs/health-checks, quoted in the table above). `/health/ready` is for the uptime bot and the Supabase keep-alive only.
- [ ] **Memory gate (Gate 0 memory item) is OPEN**: the earlier criteria failed for the local-model image; the Cloudflare-embedding image plateaus at about 165 MB locally (section above), but Render is unmeasured. No instance class or architecture change has been made.