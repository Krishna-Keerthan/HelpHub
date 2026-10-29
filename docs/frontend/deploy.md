# Deploying the frontend to Vercel

**Status: deployed (Vercel project `frontend`; its `/login` page answers 200 and Vercel checks pass on pull requests). The settings below were not re-checked against the project's dashboard; anything not confirmed is marked "unverified".** Facts marked with a source were read from the official page on 2026-10-20; anything else is marked "unverified".

## Project settings (Project Settings -> Build and Deployment)
| Setting | Value | Source / status |
|---|---|---|
| Root Directory | `frontend` | "Your app will not be able to access files outside of that directory." https://vercel.com/docs/builds/configure-a-build#root-directory and https://vercel.com/docs/monorepos (Edit next to Root Directory at import). The build needs nothing outside `frontend/` (the API types are committed in `src/lib/api/schema.d.ts`; `gen:api` reads `../docs/api` but only runs locally and in CI). |
| Framework Preset | Next.js (auto-detected) | https://vercel.com/docs/builds/configure-a-build#framework-settings. Detection on this repo: unverified. |
| Install Command | leave default, or override with `npm ci` | The page says Vercel "auto-detects the install command" from `package.json`; whether the default is `npm install` or `npm ci` is **unverified**. `npm ci` uses the committed `package-lock.json`. |
| Build Command | leave default (`npm run build`) | "Vercel checks for the `build` command in `scripts`" (same page). |
| Output Directory | default | Auto-configured for Next.js (same page). |
| Node.js Version | `24.x` | Vercel lists 24.x (default) and 22.x; `engines.node` in `package.json` overrides the dashboard value. https://vercel.com/docs/functions/runtimes/node-js/node-js-versions. This repo sets `"engines": {"node": "24.x"}` and `.nvmrc` = `24`. |
| Monorepo "Skip deployment" | optional | Skips builds when `frontend/` is unchanged; documented requirements (workspaces) are not met by this repo, so it may not apply: unverified. https://vercel.com/docs/monorepos#skipping-unaffected-projects |
| Function duration | Hobby: 300 s default and maximum | Chat route sets `maxDuration = 300`. https://vercel.com/docs/functions/limitations#max-duration |

## Environment variables (names only; set values in the dashboard)
| Name | Where it is read | Visible to the browser? | Purpose |
|---|---|---|---|
| `BACKEND_URL` | server only (`lib/server/upstream.ts`) | **No** (no `NEXT_PUBLIC_` prefix) | Base URL of the FastAPI backend, e.g. the Render URL. No trailing path. |
| `ALLOWED_ORIGINS` | server only (`lib/server/origin.ts`) | **No** | Comma-separated extra origins accepted by the Origin check on POST/DELETE. The app's own origin is always accepted; set this only for a custom domain or alias that differs from the origin the browser sees, e.g. `https://help.example.com`. Empty is valid. |
| `DEMO_EMAIL` | server only (`lib/server/auth-handlers.ts`, `handleDemoLogin`) | **No** | Email of the shared demo viewer used by "Try the demo". Optional: if any of the three demo variables is unset or empty, the button is disabled. |
| `DEMO_PASSWORD` | server only (same) | **No** | Password of the demo viewer. A secret: use the **Secret** type. Never prefix with `NEXT_PUBLIC_`. |
| `DEMO_TENANT_SLUG` | server only (same) | **No** | Workspace slug of the demo viewer. |
| `NEXT_PUBLIC_CONTACT_EMAIL` | server component `app/page.tsx` | **Yes** (public by design; it is a mailto target, **not a secret**) | Address behind the home page's "Request access" link. Never hard-coded in the repo. Optional: if unset or empty the link is hidden. Set it for Production and Preview. Next.js inlines `NEXT_PUBLIC_*` values at build time, so redeploy after changing it. |

- The only `NEXT_PUBLIC_*` variable is `NEXT_PUBLIC_CONTACT_EMAIL` (not a secret). Per the Next.js docs, only `NEXT_PUBLIC_`-prefixed variables are inlined into the browser bundle; others stay in the Node.js environment. Never put a secret in a `NEXT_PUBLIC_*` variable. (Next.js docs shipped in `node_modules/next/dist/docs/01-app/02-guides/environment-variables.md`.)
- Vercel scopes each variable to Production, Preview and/or Development, and "Any change you make to environment variables are not applied to previous deployments, they only apply to new deployments", so redeploy after changing one. https://vercel.com/docs/environment-variables
- Use the **Config** or **Secret** type as appropriate (same page); `BACKEND_URL` is not a secret.
- There are no JWT keys or provider keys in the frontend; those stay in the backend.

## Dashboard steps (you do these)
1. Vercel Dashboard -> Add New -> Project -> Import the Git repository (https://vercel.com/docs/monorepos#add-a-monorepo-through-the-vercel-dashboard).
2. Click Edit next to Root Directory and choose `frontend`.
3. Confirm Framework Preset = Next.js; leave Build/Output defaults.
4. Settings -> Build and Deployment -> Node.js Version: 24.x (or rely on `engines`).
5. Settings -> Environment Variables: add `BACKEND_URL` for Production and Preview (point Preview at a non-production backend if you have one). Add `ALLOWED_ORIGINS` only if you attach a custom domain.
6. Deploy. Open the deployment URL, then run `docs/frontend/integration-checklist.md` against it (the 4.5 MB body limit and the cold-start/streaming behaviour can only be verified on Vercel).
7. After assigning a production domain, make sure the browser origin equals the app's own origin or is listed in `ALLOWED_ORIGINS`, then redeploy.
8. Backend side: nothing for CORS (the browser only talks to the Next.js origin). The backend must be reachable from Vercel's servers; if it sleeps (Render free), the first request after idle takes about a minute (https://render.com/docs/free).

## Hobby plan terms (https://vercel.com/docs/plans/hobby)
- Free, "aimed at developers with personal projects, and small-scale applications"; "the Hobby plan restricts users to non-commercial, personal use only" (fair-use guidelines, https://vercel.com/docs/limits/fair-use-guidelines#commercial-usage; I read the Hobby page's statement, not the guidelines page itself).
- Included usage includes 1,000,000 function invocations, 4 CPU-hours active CPU, 360 GB-hours provisioned memory, 100 GB fast data transfer; exceeding a limit means waiting 30 days to use the feature again "in most cases". 100 deployments per day; runtime logs: 1 hour retention.
- Function maximum duration 300 s; request/response body limit 4.5 MB (https://vercel.com/docs/functions/limitations). See `decisions.md` D1, D5.
- Whether this project counts as non-commercial use is your call; I have not assessed it.

## Known gaps before relying on a deployment
- CI workflow (`.github/workflows/frontend.yml`) runs on GitHub: `gh run list --workflow frontend.yml` showed successful runs on pull requests and on `main` (latest 2026-10-27, run 40512245380). It only runs when `frontend/`, `docs/api/` or the workflow changes.
- Not measured: cold start through a deployed route, SSE buffering, 4 MB upload through Vercel. All listed in `integration-checklist.md`.
