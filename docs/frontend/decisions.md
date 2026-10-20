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
