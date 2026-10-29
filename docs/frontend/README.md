# HelpHub frontend

Next.js 16 (App Router, TypeScript strict, Tailwind 4) in `frontend/`. It is a backend-for-frontend: the browser talks only to this app, the Next.js server talks to FastAPI.

## Run
```bash
# Node 24 (see frontend/.nvmrc); on WSL via fnm
cd frontend
cp .env.example .env.local      # set BACKEND_URL to the running backend
npm ci
npm run dev                     # http://localhost:3000
```
The backend is started separately; this repo's frontend never starts it.

## Scripts (`frontend/package.json`)
| Script | Does |
|---|---|
| `dev` / `build` / `start` | Next.js dev server / production build / serve the build |
| `lint` | ESLint (`eslint-config-next`, TypeScript) |
| `typecheck` | `tsc --noEmit` |
| `test` | Vitest (jsdom for components, node for server code) |
| `gen:api` | Regenerate `src/lib/api/schema.d.ts` from `../docs/api/openapi.json` |

## Environment (server-only; see `.env.example`)
- `BACKEND_URL` - FastAPI base URL.
- `ALLOWED_ORIGINS` - optional extra origins for the Origin check.
No `NEXT_PUBLIC_*` variables exist. Never read or commit `.env*` files.

## Auth design (full BFF; details in `decisions.md` D1, D7, D8)
1. Login sets two httpOnly, `SameSite=Lax` cookies (`hh_at` access, `hh_rt` refresh), `Secure` except on http localhost.
2. `/api/*` forwards to FastAPI with the access token as Bearer; the server never refreshes on its own.
3. A missing/expired/rejected access token returns `401 {code:"token_expired"}`; `exp` is only a refresh hint, never authorization.
4. The client refreshes once (single-flight per tab, Web Lock across tabs) and retries the request once; no loops.
5. The refresh token is sent upstream at most once per attempt, after a repeatable `GET /health` wake-up; the cookies are cleared only when the refresh call itself returns 401.
6. Cold starts, timeouts and 5xx show a "service waking up" state and never log the user out.
7. POST/DELETE handlers reject a missing or foreign `Origin`; `proxy.ts` redirects page requests without `hh_rt` to `/login`.
8. Pages are server-rendered shells; data is fetched in client components through the single client `src/lib/api/client.ts`.

## Known limits
- Uploads are capped at 4 MiB in the browser (Vercel's 4.5 MB body limit; the backend allows 5 MiB). No second upload path.
- Chat shows a refusal only (`done.status == "no_answer"`); there is no escalation or hand-off (the backend has none).
- Residual risk AR-F1: a refresh whose response is lost can force a new login (`decisions.md` D9).
- Logout sends only the refresh token (backend contract after `a67513b`); the backend answers 204 whether or not it revoked anything, so the UI cannot tell. Unverified against the running backend.
- Layout and dark mode were **not checked in a real browser** (none available); only roles/labels are covered by tests.
- The frontend is deployed on Vercel (project `frontend`) against the Render backend, but the manual steps in `integration-checklist.md` have not been run against the deployment (its recorded runs are from 2026-10-20, local dev server only); see `deploy.md`.

## Docs
`decisions.md` (sourced decisions and risks), `integration-checklist.md` (manual real-backend steps), `deploy.md` (Vercel).
