# Frontend decisions

## D1. Auth topology: full BFF (decided 2026-10-20)
**Question:** can a Next.js route on Vercel Hobby stream a full chat answer and survive a 36 to 60 s cold start of the free Render backend? If yes, use a full BFF (the browser talks only to Next.js, which calls FastAPI). If no, use a hybrid.

**Facts** (Vercel docs, updated 2026-08-24; Render docs):
- Hobby functions with Fluid compute run up to 300 s (the default and the maximum; Pro allows 800 s), including time spent streaming. At the limit the call returns 504 `FUNCTION_INVOCATION_TIMEOUT`. Fluid compute is on by default for new projects. (https://vercel.com/docs/functions/limitations#max-duration)
- Node.js functions stream by default, and App Router route handlers can return a streamed `Response`. The Edge runtime must start responding within 25 s, so it is out for chat. (https://vercel.com/docs/functions/streaming-functions)
- A function's request or response body is capped at 4.5 MB (413 `FUNCTION_PAYLOAD_TOO_LARGE`); streaming responses are exempt from the response cap. Waiting on I/O does not count as CPU time.
- Render free web services spin down after 15 minutes without traffic, and spin-up "takes about one minute". (https://render.com/docs/free)

**Decision: full BFF.** The worst case for one chat request is about 60 s of cold start (the 36 to 60 s range comes from earlier backend measurements, not re-measured) plus the LLM answer, far below 300 s. The refresh token lives in an httpOnly cookie.

**Caveats**
- Chat route: `runtime = "nodejs"`, `maxDuration = 300`, upstream stream passed through unbuffered.
- Uploads through the BFF are capped at 4.5 MB by Vercel (D5).
- Not measured: the 300 s ceiling, and a real cold start through a deployed Vercel route.
- If no byte is sent during a cold start, intermediaries may time out the idle connection. Sending an SSE comment (`: waking`) early is untested.
- CORS is not needed (same origin). A hybrid design would need `http://localhost:3000` and the Vercel URL in the backend's allowed origins.

**Token rules**
1. Refresh token in an httpOnly cookie, `SameSite=Lax`, `Secure` except on localhost. POST and DELETE handlers check the Origin.
2. Route handlers never refresh on their own. An expired access token is returned as a 401 `token_expired`; the client refreshes once under a Web Lock (`navigator.locks`) and retries.
3. The cookie is cleared only when the refresh call itself returns 401. Timeouts, network errors and 5xx (a cold start) never log the user out: they get a bounded retry and a "service waking up" state.

## D2. Escalation: out of scope
The backend has no escalation event, status or field. The UI shows a refusal only, detected by `done.status == "no_answer"` (never by text), with a neutral message.

## D3. API contract source
Types are generated from `docs/api/openapi.json` (do not copy it). SSE event payloads are not in the schema; they are described in `docs/api/chat-stream.md`.

## D4. Node version
Pinned to **24** (`.nvmrc`, `engines.node` = `24.x`). Vercel offers 24.x (default) and 22.x and honours `engines.node` (https://vercel.com/docs/functions/runtimes/node-js/node-js-versions). The page does not mention Hobby specifically, so Hobby support is inferred.

## D5. Uploads: known limitation
- Vercel caps a function request body at 4.5 MB; the backend allows `max_upload_bytes` = 5 MiB. The Vercel cap is the tighter one.
- The UI rejects files over **4 MB** (4 * 1024 * 1024 bytes) before sending, which leaves room for multipart overhead. There is no second upload path.
- No 4 MB upload through the deployed site is recorded, so whether it passes Vercel's limit is not tested. The only 4 MiB `.txt` upload on record went through a local dev server and was **rejected** with 413 `Document is too large` (an earlier local run; see git tag `pre-prune`). A 4 MiB PDF was accepted there, which says nothing about Vercel.
- The backend also limits extracted text to `max_document_chars` = 500,000 characters (not bytes). The repo records no byte equivalent for English text, so the 4 MiB UI cap is not the effective limit for plain text, which is much lower.

## D6. Tooling notes
- `openapi-typescript@7.13.0` wants `typescript@^5.x` as a peer, but the project uses 6.0.3 (typescript-eslint needs `<6.1.0`). An npm `overrides` entry forces the peer to the project's TypeScript. Generation and `tsc` work; no deeper compatibility check was done.
- Next.js 16 renamed Middleware to **Proxy** (`src/proxy.ts`); route protection uses it.

## D7. Backend gap for "token expired"
The backend answers `401 {"detail": "Not authenticated"}` for missing, expired and invalid access tokens alike. The BFF works it out itself: it reads the access token's `exp` (unverified, a hint only) and answers `401 {"code": "token_expired"}` when the cookie is missing or past `exp`, and also maps any upstream 401 to it. The client refreshes once and retries once; a second 401, or a 401 from the refresh itself, ends the session. No backend change is needed.

## D8. Refresh design
Cookies `hh_at` (access) and `hh_rt` (refresh): httpOnly, `SameSite=Lax`, path `/`, `Secure` except on plain-http localhost. Every non-GET handler checks the Origin (own origin or `ALLOWED_ORIGINS`; a missing Origin is rejected). `lib/server/passthrough.ts` forwards requests with `Bearer` from `hh_at` and never refreshes. The client (`lib/api/authed-fetch.ts`) refreshes once through `POST /api/auth/refresh`, retries once and does not loop. `proxy.ts` only checks that `hh_rt` exists.

**Why a parallel refresh cannot trip reuse detection.** The backend revokes a whole token family if a used refresh token comes back, so a cookie must never be spent twice.
1. Same tab: callers share one in-flight promise, so N parallel 401s make one refresh call.
2. Other tabs: `navigator.locks` serialises refreshes. Inside the lock a tab compares the time its request was sent with the last refresh stamp (localStorage); if another tab refreshed since, it adopts the new cookies and sends nothing.
3. Several serverless instances: a refresh request reaches an instance only after steps 1 and 2, so at most one exists per rotation, and each instance reads the current cookie from its own request.
4. Cold start: the route first wakes the backend with `GET /health` (4 attempts of up to 25 s). If it never answers it returns `503 service_waking`; nothing was spent and the cookies are untouched. The client retries twice more with backoff.

**Residual risks** (not tested against the real backend)
- **Lost response:** if the refresh reached the backend but the answer is lost, the token may already be rotated while the browser holds the old one, and the next refresh looks like reuse and revokes the family. The route returns `502 refresh_indeterminate`, keeps the cookies and the client does not retry, but the user may be forced to log in again. A grace window or idempotency key in the backend would fix it; not done.
- Browsers without `navigator.locks` fall back to same-tab single-flight only.
- The fake-backend tests follow the documented rules; there has been no check against the real backend (rotation, reuse revocation, cold start through `/health`).
- Render's behaviour for requests held during spin-up is not documented in what was read, so `wakeBackend` treats connection errors and 503 alike as "not up yet".

## D9. Accepted risk AR-F1: refresh response lost
- **Risk:** see D8. A lost refresh answer can make the next refresh look like reuse and force a new login.
- **Why accepted:** it needs a failure in the narrow window between the backend committing the rotation and the browser receiving the answer, and the fix is a backend change.
- **How it is watched:** each occurrence logs `{"metric":"refresh_indeterminate","reason":...,"instance_count":n}` and each forced logout logs `{"metric":"forced_logout","reason":...}` (`lib/server/events.ts`; no tokens, bodies or error messages), per serverless instance, so add them up from the Vercel logs. After the first week of real use, if `refresh_indeterminate` is often followed by `forced_logout` for the same user, ask for the grace window. No threshold has been measured.

## D10. `exp` is a refresh hint, never authorization
The BFF reads `exp` (unverified) only to decide whether to refresh before calling FastAPI, with a 5 s margin for clock skew. A token whose `exp` looks valid is still forwarded and FastAPI decides. No Next.js code grants access from `exp` or any other claim.

## D11. Write controls fail closed
`DocumentsView` shows Upload only when `GET /api/auth/me` answered `admin` or `agent`, and Delete only for `admin`. While the lookup is pending, and when it fails, returns a non-2xx status, is not JSON, or has a missing or unknown role, the view is read-only. (Before this, a failed lookup left the controls visible.) The backend still enforces roles; this only decides what is shown.

## D12. Chat
- The empty state offers the five `DEMO_QUERIES` as buttons; a click sends that question.
- Citation chips open a small panel. The chat stream carries no passage text, so the panel shows the title and says the passage is not included; it does not call `POST /search` to guess it. The title comes from `GET /documents`; a document missing from the list is labelled "no longer in your library".
- Waiting states: "Searching your documents…" until the first event; after 8 s (`SLOW_FIRST_EVENT_MS`, a guess, not measured against a real cold start) "Waking the server, this can take about a minute…"; then "Found N matching passages. Writing the answer…" and a pulsing cursor (static under `prefers-reduced-motion`). Status messages are polite `role="status"`; errors are `role="alert"`.
- Errors never show status codes or backend text. A 404 forgets the stale conversation id, so the next question starts a new one. A stream that ends without `done` or `error` shows a cut-off message; this is a client-side state (`STREAM_CUT_OFF`), not a backend error code.
- Not checked when written: screenshots (no browser), and a designer's review of the 8 s threshold and the wording.

## D13. In-memory query cache
- `@tanstack/react-query` 5.104.2 (exact pin; `npm audit` showed 0 advisories then) caches `GET /documents` and `GET /auth/me` (`lib/query/hooks.ts`). A cached value is shown at once and a stale one is refetched quietly. Search, chat streams and Compare results are not cached by this.
- Fresh for **60 s** (documents) and **5 minutes** (`/auth/me`); both are choices, not measurements. `PENDING` documents are polled every 4 s.
- Nothing is written to localStorage, sessionStorage or IndexedDB (tested). A hard reload refetches.
- Security rules (tested in `DocumentsView.cache.test.tsx`):
  - The cache is cleared on login, demo login and logout, and results of in-flight old-session requests are discarded, so a viewer's cached role or list cannot appear in a later admin session. A session that ends by itself does a full page navigation, which also drops memory.
  - A role check that fails or returns garbage hides the write controls (D11); it can never grant write access.
  - A failed documents refetch keeps the last list and shows an alert plus "Showing the last list that loaded."
- The list is invalidated after an upload and after a delete.
- The cache is per tab, so an older tab can show the previous role for up to 5 minutes after a login or logout elsewhere. The backend still enforces roles.
- Not measured: how many requests this saves in real use.

## D14. Compare page
Read from `backend/app/schemas/search.py`, the search SQL and AR-11; not run against real data.
- `score` is the cosine similarity for every hit (also those only the keyword branch found); it is null in keyword mode. Results are ordered by `rrf_score` (the sum of `1/(60+rank)` over the branches that found the passage), so in the hybrid column the similarity values need not descend (from the SQL, not observed). `text_score` is not in the API, so the keyword column shows only a rank.
- Every hit starts with a line built from `vector_rank` and `keyword_rank`, such as "Vector rank 3 · Keyword rank 1"; "Similarity 0.xxx" is secondary and shown only in the vector and hybrid columns. The intro and captions say what each mode does and that the modes are not ranked against each other.
- The staged reveal is presentation only; the three requests run in parallel. Columns appear in the order Vector (at once), Keyword (+700 ms), Hybrid (+1400 ms), each only after the one before is showing. Errors show at once, and under `prefers-reduced-motion` everything appears when loaded. The 700 ms step is a choice. "Only in this list" waits until all three columns have loaded.
- Not checked when written: screenshots, a run against live search results, a designer's review of the wording.

## D15. Chat and Compare survive page changes and refresh
- **Stored (sessionStorage, per tab):** `hh_conversation` (the chat conversation id, a UUID) and `hh_compare_query` (the last Compare query). No answers, messages, passages or results are written to the browser. With storage blocked everything works and is just not restored.
- **Chat reads the server:** on mount the history is refetched from `GET /conversations/{id}/messages` (scoped by tenant and user) while the input is disabled. A 404 clears the id and shows the normal empty state; any other error shows the failure text, keeps the id and leaves the input usable.
- **Mapping:** each user message is paired with the assistant message after it. `failed` shows the generic error, `interrupted` shows the partial answer plus the cut-off message, and a user message with no assistant row is also cut off. The server does not store `cited`, so `parseCitations` recomputes it as the backend does (a parity test uses the backend fixtures). Invalid sources are dropped without renumbering the others.
- **Compare stores only the query.** Its three searches go through the in-memory cache (5 minutes, no retry; a failed search is never cached). A page change shows the cached columns at once; after F5 the searches run again and each column shows as it arrives, without the step delay.
- `endSessionState()` (`lib/session/end.ts`) clears the query cache and both stored entries on login, demo login, logout and session expiry.
- An upload or a delete clears the whole Compare cache, because the results came from the old document set.
- **Known limitations (accepted):** text typed but not sent is not saved; a stream cut by navigating away is saved by the server as `interrupted` and shows as cut off on return (a quick return can race that save and show the question with no answer); a conversation over 200 messages shows only its first 200 (no paging); sessionStorage is readable by scripts on the same origin, which is why only a UUID and a query string are kept there; the stored id is not tied to a user id, so it relies on the end-of-session clearing and on the server refusing another user's conversation (404, which clears it); Python's `strip()` and JavaScript's `trim()` treat a few unusual whitespace characters differently (for example U+FEFF) around a citation number, so `cited` could differ from the backend's in that corner (not fixed on purpose).
- After F5 the documents list and the role are fetched once each (memory cache by design).
- Not checked when written: a real browser. The 5-minute Compare window is a choice, not a measurement.

## D16. Light/dark theme toggle
- The `hh_theme` cookie holds only `light` or `dark` (anything else is ignored). It is not HttpOnly (the client sets it), `SameSite=Lax`, `Path=/`, one year, `Secure` on https, and carries no identity or token.
- With no cookie there is no `data-theme`, so the OS preference applies. The toggle starts from `matchMedia` and follows later OS changes until the user chooses.
- The root layout (a server component) reads `cookies()` and renders `<html data-theme>` only for a valid value: no inline script, no localStorage, no flash, no hydration mismatch. In `globals.css` each colour token is written once as `light-dark(<light>, <dark>)`. `scripts/contrast.mjs` checks both sides of every token and fails if a token is not in that form or the `data-theme` overrides are missing.
- `ThemeToggle` renders a same-size placeholder on the server, then the button; a click writes the cookie and sets the attribute without a reload.
- **Accepted cost:** reading `cookies()` in the root layout makes every route dynamic (rendered per request instead of served as a cached shell). The pages are thin shells whose data loads in the browser, so the cost is small; it was not measured.
- Not checked when written: a real browser. `light-dark()` depends on the browser (baseline since 2024), and a stale tab keeps its old theme until the next navigation.

## D17. Closed beta: public home page, request-access mailto, admin Users page
- **No `/register`:** the operator creates tenants with `seed_tenant.py` (runbook, "Onboarding a closed-beta workspace"). A public sign-up would need rate limiting, email verification and abuse handling that do not exist, and the free-tier backend should not take anonymous tenant creation.
- **Home page `/`:** public (the proxy exempts exactly `/`; every other path needs the `hh_rt` cookie). A visitor with `hh_rt` is redirected to `/documents`. "Try the demo" reuses the login form's demo flow.
- **Request access:** a `mailto:` built from `NEXT_PUBLIC_CONTACT_EMAIL` (set in Vercel, never in the repo). No form and no backend call, so nothing is stored. The body asks for workspace name, slug and admin email and says never to send a password. Without the variable the link is not shown.
- **Users page `/users`:** list and add only. The nav link and the page need a confirmed `admin` from `/auth/me`; anything else shows a read-only message (fail closed, as in D11). The backend still enforces `require_admin`. Errors 409, 403, 422 and 429 get fixed messages.
- **Generate password:** `crypto.getRandomValues`, 16 characters from an unambiguous set. Shown once with a copy button and held only in component state; not in storage, the cache, URLs or logs.
- **Not built:** the backend has no password reset and no deactivate or delete endpoint, so the UI has none. A user who forgets a password needs a new account with another email. Adding them is backend work and out of scope here.
- Not checked when written: a real browser (home layout, clipboard, mailto handler). The cold-start line on the home page is the free-tier "about a minute", not measured.
- **Home redesign:** sticky navbar, hero with an HTML/CSS mock chat (an illustration, not screenshots), features grid, native `<details>` FAQ and footer. Every feature and FAQ claim was checked against the code or docs (4 MB in the app, `max_document_chars` 500,000; `.txt`, `.md`, `.pdf`). Nothing is claimed about uptime, accuracy or security beyond RLS and tenant filtering.
