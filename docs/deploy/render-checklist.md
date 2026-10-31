# Render deploy checklist (Render free + Supabase free)

Built from `docs/deploy/runbook.md` (status lines updated 2026-10-29). Render-side results are owner-reported (see Status); this document's other checks were not run against Render. Items marked **unverified** are not stated by an official page.

## Status
Lines marked owner-reported were stated by the owner; this update did not check them against GitHub, Render, Vercel, Supabase or the uptime service.
- CI (`.github/workflows/ci.yml`): green (owner-reported; main CI green after PR #4).
- Supabase schema: already at migration 0012 (owner-reported).
- Demo data on Supabase: demo tenant, viewer user and 24 documents seeded (2026-10-24, owner-reported).
- Render service: live (owner-reported).
- `backend/scripts/smoke_live.py` exists (login, upload, search, chat, delete, logout). It passed twice against the Render service (owner-reported; output not recorded here).
- Vercel project: deployed (owner-reported).
- Uptime bot: configured (owner-reported; service, interval and alert rule not recorded here).
- `.github/workflows/db-ops.yml` exists: manual dispatch only, jobs `migrate` and `backup`. Whether either job has been run on GitHub is not recorded here.
- `render.yaml` does **not** exist (checked in the repo root).
- Render itself is unmeasured: no memory, region or cold-start figure from Render is recorded.
- 2026-10-29, checked from this repo's session against the live service: `/health` 200 (0.42 to 0.86 s) and `/health/ready` 200 (1.34 to 1.86 s), three runs; `scripts/smoke_live.py` passed (login, upload, search, chat, delete, logout); no `access-control-allow-origin` header for either a foreign origin or the frontend origin (the BFF design needs none).

## Health check path: use `/health`, not `/health/ready`
- `GET /health` is liveness. It returns `{"status": "ok"}` and touches nothing else (`backend/app/api/health.py`).
- `GET /health/ready` is readiness. It runs `SELECT 1` against the database through the app role and returns 503 when that fails. **It touches the database.**
- Set Render's `healthCheckPath` to `/health`. A database blip, a Supabase pause or a slow `SELECT 1` on the 0.1 CPU instance would otherwise count as a failed check, and Render restarts an instance after 60 s of failed checks (https://render.com/docs/health-checks, quoted in the runbook).
- Use `/health/ready` only for the UptimeRobot monitor (every 5 minutes) and as the Supabase keep-alive. Whether `SELECT 1` keeps Supabase from pausing is unverified.

## Before the first deploy
- [x] Supabase: roles, pgvector in `public` and schema at 0012 (owner-reported). For any later migration, run the `migrate` job (`.github/workflows/db-ops.yml`, manual dispatch, exists) before deploying. Render free has no pre-deploy command.
- [ ] `render.yaml` written (does not exist; no file in the repo): `runtime: docker`, `plan: free`, `dockerfilePath`/`dockerContext` pointing at `backend/`, `healthCheckPath: /health`, `autoDeployTrigger: off`. Free plus Docker in a Blueprint is unverified: create it and see whether the dashboard accepts it.
- [ ] Environment (names only; values in the dashboard with `sync: false`): `APP_ENV=production`, `DATABASE_URL` (app role, session pooler, `postgresql+asyncpg://` prefix), `JWT_SECRET` (32+ chars), `GROQ_API_KEY`, `EMBEDDING_PROVIDER=cloudflare`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CORS_ORIGINS`, `ALLOW_PUBLIC_REGISTRATION=false`, `PDF_TIMEOUT_SECONDS=120`, `PDF_MAX_CONCURRENCY=1`.
- [ ] `MIGRATION_DATABASE_URL` is NOT set on the Render service.
- [ ] Decide: `helphub_app` can write `alembic_version`; fix or accept before real data.

## First deploy
- [ ] Run `migrate`, then deploy manually from the dashboard (auto deploy is off).
- [ ] Watch startup: measured 40 to 56 s on a dev box, Render allows 15 minutes to bind the port. Whether the 60 s failed-check rule applies while starting is unverified; watch the first deploy.
- [ ] `GET /health` returns 200, then `GET /health/ready` returns 200 (proves the pooler connection and the runtime role).
- [ ] Record whether Render reaches Supabase over IPv6 directly (unknown); stay on the session pooler.

## Smoke checks (Day 12)
- [x] Run `backend/scripts/smoke_live.py` (exists; tenant must already exist) against the deployed URL: login, upload, search, chat, delete, logout. Passed twice (owner-reported 2026-10-26) and again on 2026-10-29. Variables: `BASE_URL`, `SMOKE_TENANT_SLUG`, `SMOKE_EMAIL`, `SMOKE_PASSWORD` (see the runbook).
- [ ] Login works within the free-tier CPU budget (measured about 0.46 s alone at 0.1 CPU).
- [ ] Wake from sleep: first request after 15 minutes idle takes about a minute (Render's figure).
- [x] CORS: no `access-control-allow-origin` header for a foreign origin or for the frontend origin (2026-10-29); the browser only talks to the BFF, so none is needed.
- [ ] Logs contain no document content, tokens, passwords or raw driver messages.

## After
- [x] Uptime bot on `/health/ready` (owner-reported configured 2026-10-26; the service and the 5 minute interval are not confirmed here).
- [ ] Backup job (`db-ops.yml`, `backup`) run once by hand; restore tested. **The job refuses to run while the repository is public, so no backups exist today.** Never store dumps as artifacts of a public repo.
- [ ] Soak and other production-readiness checks (not done).

## Open questions to settle before the demo goes live
- [ ] **Vercel Hobby function max duration vs PDF upload time.** Answered from repo docs, not yet measured on Vercel. `docs/frontend/decisions.md` (D1, "Sourced facts") records a Hobby max duration of 300 s with Fluid compute (https://vercel.com/docs/functions/limitations#max-duration, last updated 2026-08-24 per that file; not re-read here). The slowest backend upload on record was 148.3 s over the WAN (59 to 75 s with a local DB; the measurements are in git history at tag `pre-prune`), so the duration limit is not the tighter one. The tighter one is the 4.5 MB body cap (same file): the UI caps uploads at 4 MiB (`docs/frontend/README.md`) against the backend's 5 MiB (`max_upload_bytes`, `backend/app/core/config.py:71`). Still open: a real upload through a deployed Vercel route. Check it by hand on a Vercel preview (not done; Render's own upload time is also unmeasured).
- [ ] **AR-19 lockout impact on the demo.** Not answerable from the repo: it is an owner decision. Facts that are documented: login is limited to 5 attempts per 60 s per tenant and email, counted whether or not the password is right (AR-19, `docs/review/accepted-risks.md:25`); chat is limited to 10 per 60 s per user, shared by a shared account (AR-22, same file, line 28). Decide: accept (AR-19), or give each visitor their own account. What would settle it: the owner's decision recorded here, or a demo dry run with two visitors on the shared viewer login.
- [ ] **Hosted viewer account.** The runbook lists a viewer as seeded on Supabase (owner-reported). To create one through the Render API (viewer email different from the admin's, password 12 to 128 characters), see runbook "Creating the viewer through the hosted API". The viewer exists (owner-reported); whether it was created through the Render API is unverified.
- [ ] Known and accepted: client IPs behind Render's proxy are not trusted, so login limits are per account (AR-19).
