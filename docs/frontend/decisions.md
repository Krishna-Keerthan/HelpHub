# Frontend decisions

## D1. Auth topology: full BFF (decided 2026-10-20)

### Question
Can a Next.js route on Vercel Hobby stream a full chat answer and survive a 36 to 60 s upstream cold start (Render free)? If yes: full BFF. If no: hybrid.

### Sourced facts
| Claim | Source |
|---|---|
| Hobby max duration with Fluid compute is 300 s (default and maximum). Pro max is 800 s. | https://vercel.com/docs/functions/limitations#max-duration, https://vercel.com/docs/functions/configuring-functions/duration (both last updated 2026-08-24) |
| Duration includes time spent sending the response, "including streamed responses". At the limit the invocation returns 504 `FUNCTION_INVOCATION_TIMEOUT`. | same limitations page |
| Fluid compute is enabled by default (for new projects). | duration page, "Duration limits" |
| Node.js functions stream by default; Next.js App Router route handlers can return a streamed `Response`. | https://vercel.com/docs/functions/streaming-functions |
| Edge runtime must start responding within 25 s, then can stream up to 300 s. We use the Node.js runtime, so this limit does not apply, but it rules out the Edge runtime for chat (a 36 to 60 s cold start exceeds 25 s). | limitations page, "Edge runtime" |
| Request body or response body of a function is capped at 4.5 MB (413 `FUNCTION_PAYLOAD_TOO_LARGE`). Streaming functions do not have the response-size limit. | limitations page, "Request body size"; https://vercel.com/kb/guide/how-to-bypass-vercel-body-size-limit-serverless-functions |
| Render free web services spin down after 15 min without inbound traffic; spin-up "takes about one minute". | https://render.com/docs/free |
| Waiting on I/O does not count as active CPU time. | limitations page, "Cost and usage" |

### Reasoning
Worst case for one chat request: about 60 s cold start (Render docs say about one minute; the 36 to 60 s range comes from the backend shell's measurements, which I have not re-measured) plus the LLM answer. That is far below 300 s, so a Node-runtime BFF route can proxy the whole stream. Decision: **full BFF**: httpOnly cookie holds the refresh token, the Next.js server calls FastAPI.

### Consequences and caveats
- Chat route: `export const runtime = "nodejs"` and `export const maxDuration = 300`. Pass the upstream `ReadableStream` through unbuffered.
- **Upload limit:** document uploads through the BFF are capped at 4.5 MB by Vercel (source above). The backend's own upload limit was not checked here; if it is larger, uploads need a different path. Open item, unverified against the backend.
- The 300 s ceiling and the end-to-end behaviour (a real cold start through a deployed Vercel route) are **unverified**: not measured, since this shell does not start the backend or deploy. Needs one measurement once both exist.
- If the first byte is not sent during the cold start, intermediaries may time out idle connections. Whether the chat route should emit an SSE comment heartbeat while waiting for upstream is unverified; plan: send one `: waking` comment line early. Check against the real backend.
- CORS is not needed in BFF mode (browser only talks to Next.js, same origin). Backend `allow_credentials=False` is compatible. No config request to the backend shell unless we later switch to hybrid (then it needs `http://localhost:3000` and the Vercel URL in its allowed origins).

### Token handling rules (user amendments)
1. Refresh token in an httpOnly cookie, `SameSite=Lax` (so links from outside land logged in), `Secure` except on localhost dev. Origin check on POST/DELETE route handlers.
2. Route handlers and server components never refresh on their own. An expired access token is returned to the client as a distinguishable 401 (`token_expired`); the client refreshes once under a Web Lock (`navigator.locks`) and retries.
3. The cookie is cleared only when the refresh call itself returns 401. Timeouts, network errors and 5xx (cold start) never log the user out: bounded retry plus a "service waking up" state.

## D2. Escalation: out of scope
The backend has no escalation event, status or field (docs/api/chat-stream.md, "What the frontend might need"). The UI shows a refusal only, detected by `done.status == "no_answer"` (never by text), with a neutral message.

## D3. API contract source
Types are generated from `docs/api/openapi.json` once the backend shell commits it (merge `cleanup/lean` into this branch; do not copy the file). SSE event payloads are not in the schema; they come from `docs/api/chat-stream.md`.

## D4. Node version
- Pinned major: **24** (`frontend/.nvmrc` = `24`, `package.json` `engines.node` = `24.x`). Local: v24.22.0 (fnm).
- Vercel supports it: "Current available versions are: 24.x (default), 22.x"; the version is overridden by `engines.node` in `package.json`, and `24.x` deploys the latest 24.x. The page does not distinguish Hobby from other plans, so Hobby support is inferred, not stated. Source: https://vercel.com/docs/functions/runtimes/node-js/node-js-versions (last updated 2026-02-27). Node 20 deprecation date (2026-10-01) is from the same page's related-links list, not verified further.
- CI: `.github/workflows/ci.yml` has no frontend job yet and is outside this shell's tree. **Request for whoever owns CI:** add a frontend job using `actions/setup-node` with `node-version-file: frontend/.nvmrc` (the action reads `.nvmrc` or `package.json`, and the file input is ignored if `node-version` is also set; so do not set both). Source: https://github.com/actions/setup-node/blob/main/docs/advanced-usage.md. Then run `npm ci && npm run lint && npm run typecheck && npm test && npm run build` in `frontend/`. Not built, therefore not verified.

## D5. Uploads: known limitation
- Vercel caps a function request body at 4.5 MB (D1 sources). The backend's own limit is `max_upload_bytes = 5 * 1024 * 1024` (5 MiB) in `backend/app/core/config.py:70`. The Vercel cap is the tighter one.
- The UI rejects files over **4 MB** (4 * 1024 * 1024 bytes) before sending, with a clear message; that leaves room for multipart overhead under 4.5 MB. No second upload path is built.
- Whether a 4 MB file plus multipart overhead really passes Vercel's limit is unverified (not deployed).

## D6. Tooling notes
- `openapi-typescript@7.13.0` declares `typescript@^5.x` as a peer; the project uses 6.0.3 (typescript-eslint requires `<6.1.0`, so 7.x is not usable). An npm `overrides` entry forces the peer to the project TypeScript. Generation and `tsc` both succeed with it; no deeper compatibility check was done.
- Types: `npm run gen:api` reads `../docs/api/openapi.json` (the committed contract, no copy) and writes `src/lib/api/schema.d.ts`.
- Next.js 16 renamed Middleware to **Proxy** (`src/proxy.ts`); route protection uses that (node_modules/next/dist/docs/01-app/01-getting-started/16-proxy.md).

## D7. Backend gap for "token expired" (amendment 2)
The backend returns the same `401 {"detail": "Not authenticated"}` for missing, expired and invalid access tokens (`backend/app/api/deps.py:_unauthorized`; the reason is only logged). So there is no distinguishable signal from upstream. The BFF derives it itself: it decodes the access-token `exp` claim (unverified, a hint only) and answers `401 {"code": "token_expired"}` when the cookie is missing or past `exp`, and also maps any upstream 401 to `token_expired`. The client refreshes once and retries once; a second 401 or a refresh 401 ends the session. No backend change needed.
