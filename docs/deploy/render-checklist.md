# Render deploy checklist (Render free + Supabase free)

Built from `docs/deploy/deploy-plan.md` and `docs/deploy/runbook.md` (read-only research, 2026-10-21; status lines updated 2026-10-24). Nothing here has been run against Render. Items marked **unverified** are not stated by an official page.

## Status on 2026-10-24
CI, Supabase and demo-data lines are as reported by the owner; this update did not check them against GitHub or Supabase (nothing was run against any hosted service).
- CI (`.github/workflows/ci.yml`): green.
- Supabase schema: already at migration 0012.
- Demo data on Supabase: demo tenant, viewer user and 24 documents seeded (20261024).
- `backend/scripts/smoke_live.py` exists (login, upload, search, chat, delete, logout). It has not been run against Render.
- `.github/workflows/db-ops.yml` exists: manual dispatch only, jobs `migrate` and `backup`. Whether either job has been run on GitHub is not recorded here.
- `render.yaml` does **not** exist (checked in the repo root).
- Render itself is unmeasured: no deploy, no memory or latency figure from Render.

## Health check path: use `/health`, not `/health/ready`
- `GET /health` is liveness. It returns `{"status": "ok"}` and touches nothing else (`backend/app/api/health.py`).
- `GET /health/ready` is readiness. It runs `SELECT 1` against the database through the app role and returns 503 when that fails. **It touches the database.**
- Set Render's `healthCheckPath` to `/health`. A database blip, a Supabase pause or a slow `SELECT 1` on the 0.1 CPU instance would otherwise count as a failed check, and Render restarts an instance after 60 s of failed checks (https://render.com/docs/health-checks, quoted in the runbook).
- Use `/health/ready` only for the UptimeRobot monitor (every 5 minutes) and as the Supabase keep-alive. Whether `SELECT 1` keeps Supabase from pausing is unverified (deploy-plan, keep-alive section).

## Before the first deploy
- [x] CI has run green on GitHub (owner-reported 2026-10-24).
- [x] Supabase: roles, pgvector in `public` and schema at 0012 (owner-reported). For any later migration, run the `migrate` job (`.github/workflows/db-ops.yml`, manual dispatch, exists) before deploying. Render free has no pre-deploy command.
- [ ] `render.yaml` written (does not exist; no file in the repo): `runtime: docker`, `plan: free`, `dockerfilePath`/`dockerContext` pointing at `backend/`, `healthCheckPath: /health`, `autoDeployTrigger: off`. Free plus Docker in a Blueprint is unverified: create it and see whether the dashboard accepts it.
- [ ] Environment (names only; values in the dashboard with `sync: false`): `APP_ENV=production`, `DATABASE_URL` (app role, session pooler, `postgresql+asyncpg://` prefix), `JWT_SECRET` (32+ chars), `GROQ_API_KEY`, `EMBEDDING_PROVIDER=cloudflare`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CORS_ORIGINS`, `ALLOW_PUBLIC_REGISTRATION=false`, `PDF_TIMEOUT_SECONDS=120`, `PDF_MAX_CONCURRENCY=1`.
- [ ] `MIGRATION_DATABASE_URL` is NOT set on the Render service.
- [ ] Backlog BL-16 (`helphub_app` can write `alembic_version`) decided: fix or accept before real data.

## First deploy
- [ ] Run `migrate`, then deploy manually from the dashboard (auto deploy is off).
- [ ] Watch startup: measured 40 to 56 s on a dev box, Render allows 15 minutes to bind the port. Whether the 60 s failed-check rule applies while starting is unverified; watch the first deploy.
- [ ] `GET /health` returns 200, then `GET /health/ready` returns 200 (proves the pooler connection and the runtime role).
- [ ] Record whether Render reaches Supabase over IPv6 directly (unknown); stay on the session pooler.

## Smoke checks (Day 12)
- [ ] Run `backend/scripts/smoke_live.py` (exists; tenant must already exist) against the deployed URL: login, upload, search, chat, delete, logout.
- [ ] Login works within the free-tier CPU budget (measured about 0.46 s alone at 0.1 CPU, BL-13).
- [ ] Wake from sleep: first request after 15 minutes idle takes about a minute (Render's figure).
- [ ] CORS: a request from the frontend origin succeeds, another origin is rejected.
- [ ] Logs contain no document content, tokens, passwords or raw driver messages.

## After
- [ ] UptimeRobot on `/health/ready`, 5 minute interval.
- [ ] Backup job (`db-ops.yml`, `backup`) run once by hand; restore tested. Never store dumps as artifacts of a public repo.
- [ ] Soak and other production-readiness checks (not done).

## Open questions to settle before the demo goes live
- [ ] **Vercel Hobby function max duration vs PDF upload time.** If uploads pass through a Vercel function (proxy or route handler), its max duration must exceed the upload time. Backend figures at 0.1 CPU: extraction alone 9.6 to 15.7 s, whole upload 59 to 75 s under chat load with a local DB and stub LLM (runbook C8.6), up to 148 s over the WAN with Supabase (C7). Render's own figure is unmeasured. The Hobby limit was not looked up here; read it from Vercel's docs and record the number and URL. If it is below the upload time, the browser must call the backend directly.
- [ ] **Does the browser call the backend directly?** Not answered: `frontend/decisions.md` does not exist in this repo and there is no `frontend/` directory (checked 2026-10-24). Find where the frontend decision is written, read it, and record the answer. It decides the Vercel item above and what `CORS_ORIGINS` must contain (a browser-direct call needs the Vercel origin there; a server-side proxy does not).
- [ ] **AR-19 lockout impact on the demo.** Login is limited to 5 attempts per 60 s per tenant and email, counted whether or not the password is right (the rate limit is keyed per account, not per client IP). Anyone who knows the demo tenant slug and the shared viewer email can lock that login for a window with 429s, and several visitors sharing one demo account share that budget; a viewer who mistypes five times locks everyone out for 60 s. Decide: accept (AR-19), or give each visitor their own account. The chat limit (10 per 60 s per user) is shared by the same account too (AR-22).
- [ ] Known and accepted: client IPs behind Render's proxy are not trusted, so login limits are per account (AR-19).
