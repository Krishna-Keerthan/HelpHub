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

## D8. Refresh design (full BFF)
Cookies: `hh_at` (access) and `hh_rt` (refresh), both httpOnly, `SameSite=Lax`, path `/`, `Secure` except on plain-http localhost. Origin check (own origin or `ALLOWED_ORIGINS`; missing Origin rejected) on every non-GET route handler.

Flow: the browser calls `/api/*`; `lib/server/passthrough.ts` forwards with `Bearer` from `hh_at` and never refreshes. Missing/expired/rejected access token -> `401 {code:"token_expired"}` (D7). The client (`lib/api/authed-fetch.ts`) refreshes once through `POST /api/auth/refresh`, retries the original request once, and does not loop. `proxy.ts` only checks that `hh_rt` exists (redirect to `/login`).

### Why a parallel refresh cannot trip reuse detection
The backend marks a refresh token used on first spend and revokes the whole family if a used token comes back (`backend/app/services/auth.py`, `reuse_detected`). So the same cookie must never be spent twice. Layers, from the client down:
1. **Same tab:** every caller shares one in-flight promise (`refreshSession`), so N parallel 401s make one `/api/auth/refresh` call.
2. **Other tabs, same browser profile (same cookie jar):** `navigator.locks` serialises refreshes under one lock name. Inside the lock a caller compares the time its request was *sent* with the last refresh stamp (localStorage); if another tab refreshed after that, it adopts the new cookies and sends nothing. The second tab therefore reads the already-rotated cookie, never the old one.
3. **Several serverless instances:** they share no memory and need none. A refresh request reaches an instance only from layers 1-2, so at most one per rotation exists, and each instance reads the current cookie from the request itself. Different devices/browsers have separate logins and therefore separate token families.
4. **Cold start:** the refresh token is sent upstream at most once per call. The route first wakes the backend with repeatable `GET /health` (bounded: 4 attempts x 25 s); if it never answers, `503 service_waking` is returned, nothing was spent and cookies are untouched; the client retries (2 more times with backoff) and shows a "service waking up" state (`onServiceWaking`). The cookie is cleared only when the refresh call itself returns 401.

Tests: `src/lib/api/session.test.ts` (single-flight, lock/adoption, backoff, indeterminate not retried), `src/lib/server/auth-handlers.test.ts` (rotation against a fake backend that revokes the family on reuse, 6 parallel callers -> 1 rotation; the uncoordinated double-spend -> 401, cookies cleared, session ends once with no retry loop; cold start leaves cookies and token untouched), `passthrough.test.ts`, `upstream.test.ts`, `proxy.test.ts`.

### Residual risks (unverified against the real backend)
- **Lost response:** if the refresh request reached the backend but the answer is lost (timeout/5xx), the token may already be rotated while the browser still holds the old one; the next refresh then looks like reuse and revokes the family. The route reports `502 refresh_indeterminate`, keeps the cookies and the client does not auto-retry, but the user may still be forced to log in again. A short reuse grace window or idempotency key on the backend would remove this. **Config/feature request for the backend shell**; not done here.
- Browsers without `navigator.locks` fall back to same-tab single-flight only.
- Fake-backend tests model the documented rules; they are not a run against the real backend. A real-backend check (rotation, reuse revocation, cold start through `/health`) needs the backend running: not done.
- Render's behaviour for requests held during spin-up (versus connection errors/503) is not documented in the page I read, so `wakeBackend` treats both as "not up yet".

## D9. Accepted risk AR-F1: refresh response lost (token rotated, browser holds the old one)
- **Risk:** see D8 residual risks. A refresh that reached the backend but whose answer was lost can make the next refresh look like reuse and revoke the token family, forcing a new login.
- **Why accepted:** it needs a failure in the narrow window between the backend committing the rotation and the browser receiving the answer; the fix (grace window or idempotency key) is a backend change.
- **Measurement plan:** each occurrence logs one JSON line `{"metric":"refresh_indeterminate","reason":"network_or_timeout|upstream_status|bad_body","instance_count":n}`, and each forced logout logs `{"metric":"forced_logout","reason":"refresh_rejected|no_session",...}` (`lib/server/events.ts`; no tokens, bodies or error messages). Counts are per serverless instance, so total them from the Vercel logs. Review after the first week of real use: if `refresh_indeterminate` is followed by `forced_logout/refresh_rejected` for the same user more than occasionally, ask the backend shell for the grace window. No threshold has been measured yet: unverified.

## D10. `exp` is a refresh hint, never authorization
The BFF reads the access token's `exp` (unverified) only to decide whether to refresh before calling FastAPI, with a 5 s margin for clock skew (`isExpired`). A token whose `exp` looks valid is still forwarded and FastAPI decides (tests in `passthrough.test.ts`). Nothing in the Next.js code grants access from `exp` or any other claim.

## D11. UI pass, Phase 0: write controls fail closed
`DocumentsView` shows Upload only when `GET /api/auth/me` answered `admin` or `agent`, and Delete only for `admin` (the backend uses `require_admin`). While the lookup is pending, and when it fails, returns a non-2xx status, is not JSON, or has a missing or unknown role, the view is read-only (the read-only note appears once the lookup has settled). Previously a failed lookup left the controls shown. The backend still enforces roles; this only decides what is displayed. Tests: `DocumentsView.test.tsx` (viewer, pending lookup, seven failure shapes, agent, admin).
Screenshots: not captured (no browser available in this environment); see the phase report.

## D12. UI pass, Phase 1: chat
- **Empty state:** one line on what the product does plus the five `DEMO_QUERIES` as buttons; a click sends that question (no input prefill). The block disappears with the first turn.
- **Citation chips** are buttons (`aria-expanded`) that open a small panel. The chat stream carries no passage text (`docs/api/chat-stream.md`: "No chunk text or character offsets are sent"), so the panel shows the title and says the passage is not included. It does not call `POST /search` to guess the passage. The title is resolved from `GET /documents` (fetched once, on the first chip click, from the client); a document missing from the list is labelled "no longer in your library", and a failed list falls back to the title the stream carried. Phase 2 replaces this one-off fetch with the shared query cache.
- **Waiting states:** "Searching your documents…" from send until the first event; after 8 s (`SLOW_FIRST_EVENT_MS`, a guess, not measured against a real cold start) the same status switches to "Waking the server, this can take about a minute…"; after `sources` and before the first token, "Found N matching passages. Writing the answer…"; while tokens arrive a pulsing cursor (static under `prefers-reduced-motion`). All are polite `role="status"`; errors stay `role="alert"`.
- **Errors:** `chatHttpMessage` (429 with Retry-After, 503, 404, 422, 403, 5xx, other) and new in-stream codes (`llm_bad_request`, `llm_model_unavailable`); no status codes or backend text are shown. A 404 also forgets the stale conversation id so the next question starts a new conversation. A lost connection says the server could not be reached. A stream that ends without `done` or `error` shows a specific cut-off message; that is a client-side state (`STREAM_CUT_OFF`, `STREAM_CUT_OFF_MESSAGE`), not a backend `error.code`, and it is deliberately not in `IN_STREAM_ERRORS`.
- Not done: screenshots (no browser; per instruction). The 8 s threshold and the wording are unreviewed by a designer.

## D13. UI pass, Phase 2: in-memory query cache
- **What:** `@tanstack/react-query` 5.104.2 (exact pin; one dependency, `@tanstack/query-core`; `npm audit`: 0 advisories). `GET /documents` and `GET /auth/me` go through shared queries (`lib/query/hooks.ts`) used by Documents, the chat citation chips and the role check. Stale-while-revalidate: a cached value is shown at once and a stale one is refetched quietly. POST /search, /chat/stream and compare results are not cached. The browser still calls only same-origin `/api/...` through the one API client.
- **Why a library, not a custom hook:** in-flight de-duplication, stale-while-revalidate, invalidation and "keep last data on a failed refetch" are exactly its job, and a hand-rolled version would need the same tests.
- **Staleness window (a choice, not a measurement):** documents list 60 s, because uploads and deletes invalidate it anyway and only another user's changes can make it stale; a minute keeps tab-hopping instant without hiding a colleague's upload for long. `/auth/me` 5 min, because the role changes rarely and is re-checked on the next visit after that. Documents with a `PENDING` status are still polled every 4 s.
- **Memory only:** nothing is written to localStorage, sessionStorage or IndexedDB (tested). A hard reload refetches by design.
- **Security invariants (tests in `DocumentsView.cache.test.tsx`):**
  - The cache is cleared on login, demo login and logout (before and after the request), and in-flight old-session results are discarded, so a viewer's cached role or list cannot appear in a later admin session. A session that ends by itself does a full page navigation (`authedFetch.endSession`), which drops memory too, so a cached role never outlives its session.
  - Write controls still need a successful, parseable `/auth/me` with an allowed role (D11). A role revalidation that fails or returns garbage hides the write controls (fail closed): it can never grant write access, and it removes it from an admin until the next successful check.
  - A failed documents revalidation keeps the last list, shows the existing alert plus "Showing the last list that loaded.", and "Try again" refetches.
- **Invalidation:** the list is invalidated after a successful upload and after a delete (the deleted row is removed first, then the list is refetched).
- **Per tab:** the cache is per tab and does not follow a logout or login made in another tab, so an older tab can show the previous role for up to 5 minutes (`ME_STALE_MS`) until it refetches; the backend still enforces roles.
- **Negative controls run:** the new cache tests fail 5/9 against the previous `DocumentsView` (including the second-visit test), and 3/9 with the `resetSessionCache` calls removed from login/logout.
- **Not measured:** the number of requests saved over a real page tour (no browser here); the tests show only that a second visit inside the window sends none.

## D14. UI pass, Phase 3: compare page
Sources: `backend/app/schemas/search.py:30-34`, `backend/app/db/repositories/chunks.py` (SQL, lines 29-120), AR-11. Read from code; not run against real data.
- **What the numbers are:** `score` is the cosine similarity to the query for every returned hit (also those only the keyword branch found); it is null in keyword mode. Results are ordered by `rrf_score`, a sum of `1/(60+rank)` over the branches that found the passage, so in the hybrid column the cosine values need not descend (derived from the SQL, not observed). The keyword relevance (`text_score`) is not in the API, so the keyword column can show only a rank.
- **Copy:** "passages" throughout; ranks are ranks among passages. A three-sentence intro says what each mode does and does not rank the modes. Each column has a one-line caption. Keyword adds "The API returns no keyword score, only the rank."; hybrid adds "The order combines the two ranks, which is why the similarity values are not descending."
- **Every hit** starts with a why-listed line built from `vector_rank` and `keyword_rank` (not `found_by`): "Vector rank 3 · Keyword rank 1"; a single branch reads "Found by keyword only (rank 2)" in the hybrid column and "Keyword rank 2" in its own column; with neither rank, "No rank was reported for this passage". "Similarity 0.xxx" is secondary, in the vector and hybrid columns only, with a tooltip and screen-reader text.
- **Staged reveal** is presentation only: the three requests still run in parallel. A finished column appears when its turn has come (Vector at once, Keyword +700 ms, Hybrid +1400 ms) and the column before it is showing, so the order is always Vector, Keyword, Hybrid; until then it shows "Searching…". Errors show at once. Under `prefers-reduced-motion` everything appears when loaded. The 700 ms step is a choice. "Only in this list" still waits for all three columns to have loaded (not merely been revealed).
- **Tests:** `CompareView.test.tsx` and `compare.test.ts` (labels per mode, null score in keyword, why-listed cases, reveal order with fake timers, a slow first column, errors, reduced motion, badge timing). Negative control: 8 of the 19 CompareView tests fail against the previous component; the reduced-motion and badge-timing tests pass on it, since that behaviour was unchanged.
- **Not done:** screenshots (no browser); no check against live search results; wording unreviewed by a designer.

## D15. Chat and Compare survive page changes and refresh
- **What is stored (sessionStorage, per tab):** `hh_conversation` (the chat conversation id, a UUID) and `hh_compare_query` (the last submitted Compare query). Nothing else: no answers, messages, passages or search results are written to the browser. Both are read with try/catch and written with try/catch, so with storage blocked everything works and simply is not restored.
- **Why the server is read for Chat:** `GET /conversations/{id}/messages` already returns the user and assistant messages with status and sources, scoped by tenant and user, so the server stays the single source of truth and no answer text is added to browser storage. On mount the history is always refetched (`staleTime` 0), the input and Ask are disabled while "Loading conversation…" shows, and the turns are hydrated once; after that local state is authoritative as before. A 404 (gone or not ours) clears the id and shows the normal empty state; any other error shows the usual failure text, keeps the id and leaves the input usable.
- **Mapping:** each user message is paired with the assistant message after it. `complete` and `no_answer` map as they are, `failed` shows the generic error text, `interrupted` shows the partial answer plus the cut-off message (`STREAM_CUT_OFF`), and a user message with no assistant row is the cut-off state too. `cited` is not stored by the server, so `parseCitations` (`lib/ui/citations.ts`) recomputes it as the backend `parse_citations` does, against the stored number of sources; the parity test uses the backend fixtures. Sources are validated on read; an invalid one is dropped and the others keep their original `index` (never renumbered), and chips are matched by `index`, as in the live path.
- **Why only the query for Compare:** search results are stateless POSTs with no server read, and passage text should not be kept in the browser. The three searches go through the in-memory query cache (`["compare", mode, query]`, 5 minutes, no retry; a failed search throws so an error is never cached and "Try again" really searches). A page change shows cached columns at once with no request; after F5 the cache is empty, so the three searches run again, and the columns show as each arrives with no step delay. A normal click afterwards is staged as before.
- **Session end:** `endSessionState()` (`lib/session/end.ts`) clears the query cache and both entries. It replaces the `resetSessionCache()` calls in login, demo login and logout, and runs before the redirect when a session expires (the redirect drops memory but not sessionStorage).
- **Known limitations (accepted):** text typed but not sent is not saved; a stream cut by navigating away is saved by the server as `interrupted` and shows as cut off on return (a quick return can also race that save and show the question with no answer); a conversation over 200 messages shows its first 200 (no paging yet); the Compare cache is per tab; sessionStorage is readable by script on the same origin, which is why only a UUID and a query string are kept there; the stored id is not tied to a user id, so it relies on the end-of-session clearing and on the server refusing a conversation that is not the caller's (404, which clears it); Python `str.strip()` and JavaScript `trim()` treat a few exotic whitespace characters differently (for example U+FEFF, U+001C to U+001F) around a citation number, so `cited` could differ from the backend's in that corner; not fixed on purpose.
- **After F5 the documents list and the role are fetched once each** (memory cache by design, accepted by the owner); nothing about them is persisted in the browser.
- **Compare repeat click:** a repeat of the same query within 5 minutes is served from the cache (no request). An upload or a delete clears the whole Compare cache (`afterDocumentsChanged` in `lib/query/invalidate.ts`, used by both), because the results came from the old document set. It removes the entries rather than marking them stale, since a restored Compare page seeds its columns from the cache without checking staleness (tested).
- **Chat history error:** a failed (non-404) history read shows its alert until the user sends a question; the alert is dismissed when a send starts.
- **Not done:** screenshots and a run in a real browser (no browser here); the 5-minute Compare window is a choice, not a measurement.

## D16. Light/dark theme toggle (cookie, server-rendered attribute)
- **What is stored:** the `hh_theme` cookie holds only the word `light` or `dark` (`lib/theme.ts`). It is not HttpOnly (the client sets it), `SameSite=Lax`, `Path=/`, one year, `Secure` on https. It is not sensitive: it carries no identity, token or user data, and anything other than those two words is ignored.
- **First-visit rule:** no cookie means no `data-theme`, so the OS preference (`prefers-color-scheme`) applies exactly as before. The toggle starts from `matchMedia` in that case and follows later OS changes until the user chooses.
- **How it is applied:** the root layout (a server component) reads `cookies()` and renders `<html data-theme>` only for a valid value. No inline script, no localStorage, no effect that applies the theme, so there is no flash and no hydration mismatch. In `globals.css` each token is written once as `light-dark(<light>, <dark>)`; `color-scheme: light dark` follows the OS and `:root[data-theme="light" | "dark"]` pins one side. `scripts/contrast.mjs` reads both sides of every `light-dark()` token and fails if a token is not in that form or the `data-theme` overrides are missing.
- **Toggle:** `ThemeToggle` (header, between the nav and Log out; top right on the login page) renders a same-size placeholder on the server and during hydration, then the button. A click writes the cookie, sets `document.documentElement.dataset.theme` and updates its own state; no refresh or reload.
- **Accepted cost:** reading `cookies()` in the root layout makes every route dynamic (the static shells `/`, `/chat`, `/compare`, `/documents` are rendered per request). Accepted because the pages are thin shells whose data loads client-side, so the extra server render is small, and it is what avoids a flash without an inline script. The cost is a server render per navigation instead of a cached shell; not measured.
- **Not done:** no check in a real browser; light-dark() support depends on the browser (baseline since 2024); a stale tab keeps its old theme until the next navigation.

## D17. Closed beta: public home page, request-access mailto, admin Users page
- **Closed beta, no `/register`:** tenants are created by the operator with `seed_tenant.py` (runbook, "Onboarding a closed-beta workspace"). A public sign-up page would need rate limiting, email verification and abuse handling that do not exist, and the free-tier backend should not take anonymous tenant creation.
- **Home page `/`:** public (the proxy exempts exactly `/` and `/home/` for the screenshots; every other path still needs the `hh_rt` cookie). A visitor with `hh_rt` is redirected to `/documents`. "Try the demo" reuses the login form's demo flow (`useDemoLogin`).
- **Request access:** a `mailto:` built from `NEXT_PUBLIC_CONTACT_EMAIL` (set in Vercel, never in the repo). No form and no backend call, so nothing is stored. The body template asks for workspace name, slug and admin email and says never to send a password. If the variable is missing the link is not rendered.
- **Users page `/users`:** list and add only. The nav link and the page require a confirmed `admin` from `/auth/me`; pending, failed or unknown means a read-only message (fail closed, as D11). The backend still enforces `require_admin`. Errors 409, 403, 422, 429 get fixed messages; backend text is never shown.
- **Generate password:** `crypto.getRandomValues`, 16 characters, rejection-sampled from an unambiguous charset. Shown once with a copy button; held in component state only, cleared on hide, on a successful add and on unmount. Not in storage, the query cache, URLs or logs.
- **Not built:** no password reset and no deactivate/delete endpoint exist on the backend, so the UI has none (`is_active` is displayed only). A user who forgets a password needs a new account with another email until those endpoints exist. Adding them is backend work and out of scope for this change.
- **Not done:** no check in a real browser (home layout, clipboard, mailto handler); the cold-start line is the free-tier "about a minute" from the deploy notes, not measured.

