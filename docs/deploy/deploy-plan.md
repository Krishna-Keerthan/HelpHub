# Deploy plan (Render free + Supabase free)

Written 2026-10-20. Sources were fetched that day; anything not stated by an official page is marked **unverified**. Nothing here has been run against Render or Supabase.

## Findings

| Question | Answer | Source |
|---|---|---|
| (a) Pre-deploy command on Render free | **No.** "The pre-deploy command is available for paid web services, private services, and background workers." The Blueprint spec lists `preDeployCommand` with no plan note other than "Not supported for workflows", so the Blueprint field would not help a free service. | https://render.com/docs/deploys.md ; https://render.com/docs/blueprint-spec.md |
| (b) Blueprint with a free Docker web service | **Probably, unverified as a combination.** The spec lists `runtime: docker` ("for services that build an image from a Dockerfile"), `plan: free` ("0.1 CPU, 512 MB"), `dockerfilePath` and `dockerContext` (relative to the repo root; defaults `./Dockerfile` and the repo root), `healthCheckPath`, `autoDeployTrigger` (`commit`, `checksPass`, `off`) and env vars as `key` + `value`, `sync: false` (prompt in the dashboard) or `generateValue: true`. No page I fetched says free + docker is allowed or forbidden (https://render.com/docs/free.md does not mention Docker). Test: create the Blueprint and see whether the dashboard accepts it. | https://render.com/docs/blueprint-spec.md ; https://render.com/docs/free.md |
| (c) UptimeRobot free | 5-minute interval, 50 monitors (https://uptimerobot.com/pricing.md). Commercial use: the Terms say "UptimeRobot is available for any use, including commercial and business use" (https://uptimerobot.com/terms, page modified 2026-06-24); the knowledge hub says the same for the Free plan (https://uptimerobot.com/knowledge-hub/monitoring/uptimerobot-for-client-work/). Some third-party sites claim a non-commercial restriction from late 2024; the official pages above do not show one. | as listed |
| (d) Does `SELECT 1` count against the Supabase pause | **Unverified.** The page says a free project is inactive if it "does not receive sufficient user database activity over the past week" and lists "Making API calls to your project or sending requests via your connected application" as ways to keep it active. It does not say whether a bare `SELECT 1` or a health check counts. | https://supabase.com/docs/guides/platform/free-project-pausing |
| (e) GitHub Actions artifacts | Download needs read access to the repository ("Read access to the repository is required to perform these steps", https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/downloading-workflow-artifacts). The page does not spell out the public-repo case. Inference (not stated by GitHub): on a public repo everyone with a GitHub account has read access, so every artifact there is readable by others. Retention: default 90 days; configurable 1 to 90 days (public) and 1 to 400 days (private) (https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository). Free plan artifact storage: 500 MB (https://docs.github.com/en/actions/reference/limits). Per-artifact size limit: not found. | as listed |

The repository is currently **private** (`gh repo view`: PRIVATE). That can change, so the backup design must not depend on it.

## Migration step (recommended)
- Render free has no pre-deploy command, so migrations run from GitHub Actions: `.github/workflows/db-ops.yml`, job `migrate`, **manual dispatch only**. It runs `uv run alembic upgrade head` with `MIGRATION_DATABASE_URL` (the `helphub_owner` role over the Supabase **session pooler**, from an environment secret). The runtime role (`helphub_app`) and `postgres` are never used for migrations. The runtime Render service does not get `MIGRATION_DATABASE_URL`.
- Order for a release: run `migrate`, then deploy. Set `autoDeployTrigger: off` in `render.yaml` so a push cannot deploy code that expects a schema not yet migrated; deploy from the dashboard or a manual deploy after `migrate` succeeds. Migrations must stay backward compatible with the previous release for the minutes between the two steps (not enforced by anything today).
- The job uses a GitHub **environment** (`production`) so the secret is only available to that job and a required reviewer can be added. Enforcing reviewers needs a repo setting that this change does not make.

## Backups (Supabase free has none)
- Approach: `db-ops.yml`, job `backup`, **manual dispatch only**: `pg_dump` as `helphub_owner` over the session pooler, encrypted with `gpg --symmetric --cipher-algo AES256` using `BACKUP_PASSPHRASE` from the environment secret, uploaded as an Actions artifact with `retention-days: 14`.
- **Fail-closed on visibility:** the job first checks `github.event.repository.private == true` and stops otherwise. Because artifacts of a public repository are likely readable by any GitHub user (inference above), **database dumps are never stored as artifacts of a public repo**, encrypted or not. If the repo is ever made public, move backups to storage you control (an object store with a write-only key; needs an account, not set up) and delete the job.
- Size: the 500 MB free-plan artifact storage is shared with everything else; a dump must stay well below it. Not measured for this database. At the measured 6,805 B per chunk (docs/cleanup/b1-measurements.md) a full 500 MB database would not fit; a demo-sized one is tiny.
- Unverified: whether `pg_dump` works through the Supabase session pooler with the owner role, and the server version versus the client version on the runner (a mismatch makes `pg_dump` refuse). Test once by hand before relying on it. Restore is not tested either; a backup that was never restored is not a backup.
- Not enabled: no `schedule:` trigger. Add one only after one manual run is checked and the repo visibility rule is accepted.

## Keep-alive
- Render spins a free web service down after 15 minutes without inbound traffic and wakes it in about a minute (https://render.com/docs/free.md). Free instance hours: 750 per workspace per month; one always-on service uses about 744 in a 31-day month, so a second free service would exceed it.
- UptimeRobot monitor on `GET /health/ready` every 5 minutes (HTTP 200 expected). `/health/ready` runs `SELECT 1` against Supabase. Whether that keeps Supabase from pausing is **unverified** (d).
- Hedge for (d): a weekly run of `backend/scripts/smoke_live.py` (real reads and writes through the app) against the live URL. Until a schedule is allowed, run it by hand weekly. Verification of whether `SELECT 1` alone suffices = leave the project untouched by anything else for more than a week and see whether it pauses (not done).

## Blueprint env var names (`render.yaml`, to be written at deploy time)
Names only, from `app/core/config.py` and `docs/deploy/runbook.md`. Values marked secret use `sync: false`.
| Name | Value |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | secret (app role, session pooler) |
| `JWT_SECRET` | secret, or `generateValue: true` (32+ chars needed; the generated length is a base64 of 256 bits, so long enough, not verified against the validator) |
| `GROQ_API_KEY` | secret (required when `APP_ENV=production`) |
| `EMBEDDING_PROVIDER` | `cloudflare` (also the Dockerfile default) |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | secret |
| `CORS_ORIGINS` | the frontend origin(s) |
| `ALLOW_PUBLIC_REGISTRATION` | `false` |
| `PDF_TIMEOUT_SECONDS` | `120` |
| `PDF_MAX_CONCURRENCY` | `1` |
| `PORT` | set by Render |
`MIGRATION_DATABASE_URL` is deliberately absent. The runbook's `EMBEDDING_THREADS` / `HF_HUB_OFFLINE` entries no longer apply (no local model in the image).
