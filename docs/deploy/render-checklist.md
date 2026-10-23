# Render deploy checklist (Render free + Supabase free)

Built from `docs/deploy/deploy-plan.md` and `docs/deploy/runbook.md` (read-only research, 2026-10-21). Nothing here has been run against Render or Supabase. Items marked **unverified** are not stated by an official page.

## Health check path: use `/health`, not `/health/ready`
- `GET /health` is liveness. It returns `{"status": "ok"}` and touches nothing else (`backend/app/api/health.py`).
- `GET /health/ready` is readiness. It runs `SELECT 1` against the database through the app role and returns 503 when that fails. **It touches the database.**
- Set Render's `healthCheckPath` to `/health`. A database blip, a Supabase pause or a slow `SELECT 1` on the 0.1 CPU instance would otherwise count as a failed check, and Render restarts an instance after 60 s of failed checks (https://render.com/docs/health-checks, quoted in the runbook).
- Use `/health/ready` only for the UptimeRobot monitor (every 5 minutes) and as the Supabase keep-alive. Whether `SELECT 1` keeps Supabase from pausing is unverified (deploy-plan, keep-alive section).

## Before the first deploy
- [ ] CI has run green on GitHub at least once (gate, audit, image and secrets jobs). It has never run yet.
- [ ] Supabase: roles `helphub_owner` and `helphub_app` exist; pgvector in schema `public`; run the `migrate` job (`.github/workflows/db-ops.yml`, manual dispatch) so the schema is at head before any deploy. Render free has no pre-deploy command.
- [ ] `render.yaml` written (does not exist yet): `runtime: docker`, `plan: free`, `dockerfilePath`/`dockerContext` pointing at `backend/`, `healthCheckPath: /health`, `autoDeployTrigger: off`. Free plus Docker in a Blueprint is unverified: create it and see whether the dashboard accepts it.
- [ ] Environment (names only; values in the dashboard with `sync: false`): `APP_ENV=production`, `DATABASE_URL` (app role, session pooler, `postgresql+asyncpg://` prefix), `JWT_SECRET` (32+ chars), `GROQ_API_KEY`, `EMBEDDING_PROVIDER=cloudflare`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CORS_ORIGINS`, `ALLOW_PUBLIC_REGISTRATION=false`, `PDF_TIMEOUT_SECONDS=120`, `PDF_MAX_CONCURRENCY=1`.
- [ ] `MIGRATION_DATABASE_URL` is NOT set on the Render service.
- [ ] Backlog BL-16 (`helphub_app` can write `alembic_version`) decided: fix or accept before real data.

## First deploy
- [ ] Run `migrate`, then deploy manually from the dashboard (auto deploy is off).
- [ ] Watch startup: measured 40 to 56 s on a dev box, Render allows 15 minutes to bind the port. Whether the 60 s failed-check rule applies while starting is unverified; watch the first deploy.
- [ ] `GET /health` returns 200, then `GET /health/ready` returns 200 (proves the pooler connection and the runtime role).
- [ ] Record whether Render reaches Supabase over IPv6 directly (unknown); stay on the session pooler.

## Smoke checks (Day 12)
- [ ] `backend/scripts/smoke_live.py` does not exist yet: register or seed, upload, search, chat, delete against the deployed URL.
- [ ] Login works within the free-tier CPU budget (measured about 0.46 s alone at 0.1 CPU, BL-13).
- [ ] Wake from sleep: first request after 15 minutes idle takes about a minute (Render's figure).
- [ ] CORS: a request from the frontend origin succeeds, another origin is rejected.
- [ ] Logs contain no document content, tokens, passwords or raw driver messages.

## After
- [ ] UptimeRobot on `/health/ready`, 5 minute interval.
- [ ] Backup job (`db-ops.yml`, `backup`) run once by hand; restore tested. Never store dumps as artifacts of a public repo.
- [ ] Soak and other production-readiness checks (not done).
- [ ] Known and accepted: client IPs behind Render's proxy are not trusted, so login limits are per account (AR-19).
