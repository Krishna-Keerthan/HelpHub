# Render deploy checklist (Render free + Supabase free)

Built from `docs/deploy/runbook.md` (updated 2026-10-31). Render-side results are owner-reported (see Status); the other checks were not run against Render. "Not known" means no official page states it.

## Status
Lines marked owner-reported come from the owner and have not been checked against GitHub, Render, Vercel, Supabase or the uptime service.
- CI (`.github/workflows/ci.yml`) is green on `main` (checked 2026-10-31).
- Supabase is at migration 0012, and the demo tenant, a viewer user and 24 documents were seeded on 2026-10-24 (owner-reported).
- The Render service is live, the Vercel project is deployed, and the uptime bot is set up (owner-reported; the bot's service, interval and alert rule are not recorded here).
- `.github/workflows/db-ops.yml` has two manual jobs, `migrate` and `backup`. Whether either has been run on GitHub is not recorded. There is no `render.yaml`.
- Render itself is not measured: no memory, region or cold-start figure from Render is recorded.
- Checked from this repo against the live service on 2026-10-29: `/health` 200 (0.42 to 0.86 s) and `/health/ready` 200 (1.34 to 1.86 s) in three runs; `scripts/smoke_live.py` passed; no `access-control-allow-origin` header for a foreign origin or for the frontend origin (the browser only talks to the BFF, so none is needed).
- Checked again on 2026-10-31 after the owner redeployed the backend (the deployed commit is not recorded here; the Render deploy page shows it): `/health` 200 (0.43 to 1.00 s), `/health/ready` 200 (1.26 to 2.89 s), `HEAD /health` 200 (the HEAD fix is live), `GET /documents` returns `X-Total-Count: 24`, `scripts/smoke_live.py` passed, and a one-page PDF uploaded through `/documents/upload` reached READY in 9.21 s, was found by search and was deleted (document count back to 24). Not confirmed from outside: that pypdf 6.21.4 is the installed version.

## Health check path: use `/health`, not `/health/ready`
- `GET /health` only says the process is up (`{"status": "ok"}`) and touches nothing else (`backend/app/api/health.py`).
- `GET /health/ready` runs `SELECT 1` against the database as the app role and returns 503 if that fails, so it touches the database.
- Set Render's `healthCheckPath` to `/health`. A database blip, a Supabase pause or a slow `SELECT 1` on the 0.1 CPU instance would otherwise count as a failed check, and Render restarts an instance after 60 s of failed checks (https://render.com/docs/health-checks).
- Use `/health/ready` only for the UptimeRobot monitor (every 5 minutes) and as the Supabase keep-alive. Not known: whether `SELECT 1` keeps Supabase from pausing.

## Before the first deploy
- [x] Supabase roles, pgvector in `public` and the schema at 0012 are in place (owner-reported). For a later migration, run the `migrate` job (`db-ops.yml`, manual) before deploying; Render free has no pre-deploy command.
- [ ] Write `render.yaml` (it does not exist): `runtime: docker`, `plan: free`, `dockerfilePath` and `dockerContext` pointing at `backend/`, `healthCheckPath: /health`, `autoDeployTrigger: off`. Whether a Blueprint accepts free plus Docker is not known; create it and see.
- [ ] Environment (names only; values go in the dashboard with `sync: false`): `APP_ENV=production`, `DATABASE_URL` (app role, session pooler, `postgresql+asyncpg://` prefix), `JWT_SECRET` (32+ characters), `GROQ_API_KEY`, `EMBEDDING_PROVIDER=cloudflare`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CORS_ORIGINS`, `ALLOW_PUBLIC_REGISTRATION=false`, `PDF_TIMEOUT_SECONDS=120`, `PDF_MAX_CONCURRENCY=1`.
- [ ] `MIGRATION_DATABASE_URL` is NOT set on the Render service.
- [ ] Decide: `helphub_app` can write `alembic_version`; fix it or accept it before real data.

## First deploy
- [ ] Run `migrate`, then deploy manually from the dashboard (auto deploy is off).
- [ ] Watch startup. It took 40 to 56 s on a dev box, and Render allows 15 minutes to bind the port. Not known: whether the 60 s failed-check rule applies while the service is still starting.
- [x] `GET /health` returns 200, then `GET /health/ready` returns 200 (shows the pooler connection and the runtime role work). Checked 2026-10-29 and 2026-10-31.
- [ ] Find out whether Render reaches Supabase over IPv6 directly (not known); stay on the session pooler.

## Smoke checks
- [x] Run `backend/scripts/smoke_live.py` against the deployed URL (the tenant must already exist): login, upload, search, chat, delete, logout. Passed twice (owner-reported 2026-10-26) and again on 2026-10-29 and 2026-10-31. Variables: `BASE_URL`, `SMOKE_TENANT_SLUG`, `SMOKE_EMAIL`, `SMOKE_PASSWORD` (see the runbook).
- [x] PDF upload through the live service (`POST /documents/upload`): READY, searchable, deleted afterwards (2026-10-31). `smoke_live.py` only uploads text, so this was a separate check.
- [ ] Login stays fast enough on the free-tier CPU (about 0.46 s alone at 0.1 CPU in a local test).
- [ ] Wake from sleep: the first request after 15 minutes idle takes about a minute (Render's figure; not measured here).
- [x] CORS: no `access-control-allow-origin` header for a foreign origin or for the frontend origin (2026-10-29).
- [ ] Logs contain no document content, tokens, passwords or raw driver messages.

## After
- [x] Uptime bot on `/health/ready` (owner-reported, set up 2026-10-26; the service and the 5 minute interval are not confirmed here).
- [ ] Run the `backup` job once by hand and test a restore. **The job refuses to run while the repository is public, so no backups exist today.** Never store dumps as artifacts of a public repo.
- [ ] Soak test and other production-readiness checks (not done).

## Open questions before the demo goes live
- [ ] **Vercel Hobby function limit vs PDF upload time.** Not measured on Vercel. `docs/frontend/decisions.md` (D1) records a Hobby maximum of 300 s with Fluid compute (https://vercel.com/docs/functions/limitations#max-duration). The slowest backend upload on record took 148.3 s over the internet (59 to 75 s with a local database; the measurements are in git history at tag `pre-prune`), so the duration limit is not the tighter one. The tighter one is the 4.5 MB body cap: the UI caps uploads at 4 MiB (`docs/frontend/README.md`) against the backend's 5 MiB. Still open: a real upload through a deployed Vercel route, to be tried by hand on a Vercel preview. Render's own upload time is not measured either.
- [ ] **Demo lockout (AR-19).** This is the owner's decision. Login is limited to 5 attempts per 60 s per tenant and email, counted whether or not the password is right (AR-19, `docs/review/accepted-risks.md`), and chat is limited to 10 per 60 s per user, shared by a shared account (AR-22). Either accept it, or give each visitor their own account. A demo dry run with two visitors on the shared viewer login would show how bad it is.
- [ ] **Hosted viewer account.** A viewer was seeded on Supabase (owner-reported). To create one through the Render API (viewer email different from the admin's, password 12 to 128 characters), see "Creating the viewer through the hosted API" in the runbook. Whether the existing viewer was created that way is not known.
- [ ] Known and accepted: client IPs behind Render's proxy are not trusted, so login limits are per account (AR-19).
