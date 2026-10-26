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
- [ ] **Vercel Hobby function max duration vs PDF upload time.** Answered from repo docs, not yet measured on Vercel. `docs/frontend/decisions.md` (D1, "Sourced facts") records a Hobby max duration of 300 s with Fluid compute (https://vercel.com/docs/functions/limitations#max-duration, last updated 2026-08-24 per that file; not re-read here). The slowest backend upload on record is 148.3 s over the WAN (runbook C7), 59 to 75 s with a local DB (C8.6), so the duration limit is not the tighter one. The tighter one is the 4.5 MB body cap (same file): the UI caps uploads at 4 MiB (`docs/frontend/README.md`) against the backend's 5 MiB (`max_upload_bytes`, `backend/app/core/config.py:71`). Still open: a real upload through a deployed Vercel route. It is verified by integration-checklist 4.1 to 4.4 on a Vercel preview (not run; Render's own upload time is also unmeasured).
- [x] **Does the browser call the backend directly?** No. `docs/frontend/decisions.md` D1 (decided 2026-10-20) chose a full BFF: the browser talks only to Next.js, and the Next.js server calls FastAPI. Correction to the earlier text of this item: `frontend/` and `docs/frontend/decisions.md` do exist (the earlier check looked for `frontend/decisions.md`). Consequence stated there: CORS is not needed in BFF mode, so `CORS_ORIGINS` does not need the Vercel origin; a hybrid design would need `http://localhost:3000` and the Vercel URL. Not verified on a deployed Vercel project (`docs/frontend/deploy.md`: "not deployed"). The CORS smoke check below still applies if `CORS_ORIGINS` is set.
- [ ] **AR-19 lockout impact on the demo.** Not answerable from the repo: it is an owner decision. Facts that are documented: login is limited to 5 attempts per 60 s per tenant and email, counted whether or not the password is right (AR-19, `docs/review/accepted-risks.md:25`); chat is limited to 10 per 60 s per user, shared by a shared account (AR-22, same file, line 28). Decide: accept (AR-19), or give each visitor their own account. What would settle it: the owner's decision recorded here, or a demo dry run with two visitors on the shared viewer login.
- [ ] **Hosted viewer account.** The runbook lists a viewer as seeded on Supabase (owner-reported). To create one through the Render API (viewer email different from the admin's, password 12 to 128 characters), see runbook "Creating the viewer through the hosted API". Not run against Render.
- [ ] Known and accepted: client IPs behind Render's proxy are not trusted, so login limits are per account (AR-19).
