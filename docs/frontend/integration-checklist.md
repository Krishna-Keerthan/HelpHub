# Integration checklist (manual, real backend)

Not run yet. Every "Expected" below is a prediction from the code and tests, **unverified** until you run it. Record the observed result next to each step.

## 0. Setup
1. Start the backend yourself (docker services + `uv run fastapi dev app/main.py` from `backend/`); note its URL, e.g. `http://localhost:8000`.
2. `cd frontend && cp .env.example .env.local` and set `BACKEND_URL=<backend url>` (do not paste secrets anywhere else). `npm run dev` -> app at `http://localhost:3000`. Use this as `$APP` below.
3. Create a workspace and user directly on the backend (the UI has no register screen):
   `curl -s -X POST $BACKEND/auth/register -H 'Content-Type: application/json' -d '{"email":"qa@example.com","password":"<choose>","tenant_name":"QA","tenant_slug":"qa"}'`
   Expected: 2xx with tokens in the body. (Discard them.)
4. Open DevTools -> Application -> Cookies -> `http://localhost:3000` and Network (Preserve log on). Cookies `hh_at` / `hh_rt` are httpOnly: visible here, not in JS.

## 1. Login and route protection
1. Visit `$APP/documents` with no cookies. Expected: redirect to `/login?next=%2Fdocuments`.
2. Log in with workspace `qa`, the email and password. Expected: `POST /api/auth/login` 200, body `{"ok":true}` (no tokens in the body), then land on `/documents`.
3. Cookies: `hh_at` and `hh_rt` both `HttpOnly`, `SameSite=Lax`, Path `/`, **not** `Secure` (http localhost). `hh_at` lifetime equals the access token's (the backend default is 15 minutes; the local app overrides it to 60 minutes, exp minus iat = 3600 s, so expect Max-Age 3599 locally), `hh_rt` ~7 days.
4. Wrong password. Expected: "Email, password or workspace is wrong.", no cookies set.
5. `$APP/login?next=//evil.test` then log in. Expected: lands on `/documents`, not off-site.

## 2. Refresh rotation
1. Copy the current `hh_rt` value (call it **RT-A**). Delete only the `hh_at` cookie.
2. On `/documents` click **Refresh**. Expected in Network: `GET /api/documents` -> 401 `{"code":"token_expired"}`; then exactly one `POST /api/auth/refresh` -> 200; then the `GET` is retried -> 200 and the list shows.
3. Cookies: `hh_rt` changed to a new value (**RT-B** != RT-A), `hh_at` is back.
4. Server console shows no token text; no `refresh_indeterminate` / `forced_logout` line.
5. Parallel: open two tabs on `/documents`. Delete `hh_at`. Click **Refresh** in both within about a second. Expected: across both tabs' Network panels exactly one `POST /api/auth/refresh`; both lists load; backend log shows no "refresh token reuse".
6. Also in one tab: delete `hh_at` and open `/chat` and `/documents` quickly (or press Refresh several times fast). Expected: still one refresh per rotation.

## 3. Replaying an old refresh token (family revocation)
1. After step 2.3 you hold RT-A (already spent) and RT-B (current, in the browser).
2. `curl -i -X POST $APP/api/auth/refresh -H "Origin: $APP" -H "Cookie: hh_rt=<RT-A>"`
   Expected: `401 {"code":"session_expired"}`, `Set-Cookie` lines clearing `hh_at` and `hh_rt` (Max-Age=0); backend log "refresh token reuse"; Next server logs `{"metric":"forced_logout","reason":"refresh_rejected",...}`.
3. Back in the browser (still holding RT-B, which the backend should now have revoked): delete `hh_at`, click **Refresh**. Expected: `POST /api/auth/refresh` -> 401, then redirect to `/login?next=...`; cookies cleared; the original request is not retried (no loop).
4. Origin check: `curl -i -X POST $APP/api/auth/refresh -H "Origin: http://evil.test" -H "Cookie: hh_rt=x"` -> `403 {"code":"bad_origin"}`; same without any `Origin` header -> 403.

## 4. 4 MB upload through the Next server
Log in again first.
1. `head -c 4194304 /dev/urandom | base64 | head -c 4194304 > /tmp/exact-4mb.txt` (exactly 4 MiB of text). Upload it in the UI. Expected: accepted by the client, `POST /api/documents/upload` -> 201 (or 200), document appears, status PENDING then READY after **Refresh**. If the backend answers 415 for `.txt`, repeat with a real PDF of just under 4 MB and note which types the backend accepts.
2. `head -c 4194305 /dev/urandom | base64 | head -c 4194305 > /tmp/over-4mb.txt`. Expected: rejected in the browser with "limited to 4 MB", **no** request in Network.
3. Bypass the UI cap to see Vercel/Next behaviour: `curl -i -X POST $APP/api/documents/upload -H "Origin: $APP" -H "Cookie: hh_at=<value from DevTools>" -F file=@/tmp/over-4mb.txt`. Locally expect the backend's answer (limit is 5 MiB, so ~4.0 MiB still passes; try a 6 MiB file for 413). The **4.5 MB Vercel limit only exists on Vercel**: repeat on a Vercel preview deployment and expect `413 FUNCTION_PAYLOAD_TOO_LARGE` above ~4.5 MB. Local dev cannot verify this.
4. Delete the document in the UI. Expected: confirm dialog; cancel sends nothing; confirm sends `DELETE /api/documents/<id>` -> 204 and the row disappears.

## 5. Chat stream end to end
(Needs documents in READY state and the embedding/LLM providers configured.)
1. Ask a question the documents answer. Expected: `POST /api/chat/stream` 200 `text/event-stream`; answer grows incrementally (check it is not delivered all at once: buffering is unverified); source chips show only the cited `[n]` titles.
2. Ask something unrelated. Expected: refusal text "I couldn't find anything in your documents that answers this question." and no source chips (backend `done.status = no_answer`).
3. Ask a second question in the same page. Expected: request body carries the `conversation_id` from the first answer.
4. Send more than the chat limit within 60 s (default 10). Expected: "Too many requests. Try again in N seconds." with N from `Retry-After`.
5. Embedding failure (only if you can make the provider fail, e.g. invalid key in the backend env on your side): expected in-stream `error` `embedding_unavailable` shown as "Search is temporarily unavailable…". Skip if you cannot trigger it; mark skipped, not passed.
6. Expired access token in the middle: delete `hh_at`, then ask. Expected: one refresh, then the chat request is retried and streams normally.

## 6. Backend cold start
Only meaningful against a sleeping backend (Render free, after ~15 min idle) or by simulating: stop the backend (you), keep the app running.
1. With the backend **stopped**: delete `hh_at`, click **Refresh** on `/documents`. Expected after the wake-up attempts (4 x up to 25 s plus 2 s gaps, then client backoff of 2 more tries): amber "service is waking up" banner, and a message with "waking up" in the list area; **`hh_rt` is still present**, you are **not** redirected to `/login`; backend request log shows no `/auth/refresh` call (token never sent).
2. Start the backend while the banner shows. Click **Refresh** again. Expected: refresh succeeds with the same `hh_rt` as before the outage (RT unchanged by the failed attempts), list loads, banner gone.
3. Login while the backend is stopped. Expected: "The service is waking up…" message, no cookies; works after the backend is up.
4. Real Render sleep: let the service idle 15+ minutes, then act in the UI. Record the observed time to first byte for (a) `GET /api/documents` and (b) a chat request, and whether Render holds the request or returns an error during spin-up (unverified). Chat stream through a **deployed Vercel** route during a 36-60 s wake is also unverified: run it once there and note whether an SSE heartbeat is needed.
5. Lost-response case (AR-F1) cannot be triggered by hand reliably; check the logs for `refresh_indeterminate` over the first week of use.

## 7. Logout
Click **Log out**. Expected: `POST /api/auth/logout` 200 `{"sent":true}`, cookies cleared, landing on `/login`; the upstream request carries the refresh token in the body and **no** `Authorization` header; replaying the old RT via curl as in 3.2 returns 401. Repeat after deleting `hh_at` (expired access token): expected the same result, because logout no longer needs it. Replaying logout with an already revoked or tampered token via curl against the BACKEND should also return 204 (same answer either way).

## Observed run: 2026-10-20 (partial, terminal only)

Setup: `TEST_EMAIL`, `TEST_PASSWORD`, `BACKEND_URL` were set. Backend at `http://127.0.0.1:8000` (`/health` 200). Own dev server: `npm run dev -p 3100` with `BACKEND_URL` from the shell (no `.env.local`). Backend not modified.

**Blocker for every step that needs a session:** the shell has no tenant slug (login needs `tenant_slug`). `qa` failed (401), and `POST /auth/register` answers 403 `Registration is disabled`, so step 0.3 cannot create a workspace. No further slugs were guessed. The authenticated parts of 1.2-1.3, 2, 3.2-3.3, 4, 5 and 7 are **not run** until a slug is provided (e.g. `TEST_TENANT_SLUG`).

| Step | Expected | Observed |
|---|---|---|
| 1.1 | redirect to `/login?next=%2Fdocuments` | 307 to `/login?next=%2Fdocuments`. Matches. |
| 1.2-1.3 | login 200, cookie flags/expiry | Not run (no slug). |
| 1.4 | wrong password: error, no cookies | `POST /api/auth/login` 401 `{"code":"invalid_credentials"}`, 0 `Set-Cookie`. Matches (UI text not checked). |
| 1.5 | `next=//evil.test` stays on-site | Not run: browser behaviour. |
| 2 | refresh rotation, retry, parallel tabs | Not run (no session; Web Lock and tab behaviour need a browser). Only: `GET /api/documents` with no cookies gives 401 `{"code":"token_expired"}`. Matches. |
| 3.2 | replay spent RT-A: 401, cookies cleared | Not run with a real RT. With a bogus RT: 401 and both cookies cleared (`Max-Age=0`, HttpOnly, SameSite=lax). Backend "refresh token reuse" log and `forced_logout` line not checked. |
| 3.3 | RT-B rejected after reuse, no loop | Not run (no session; the redirect needs a browser). |
| 3.4 | bad or missing Origin gives 403 `bad_origin` | Both 403 `{"code":"bad_origin"}`. Matches. |
| 4.1-4.4 | 4 MB upload, over-limit, delete | Not run (no session). 4.2 and the 4.5 MB Vercel limit also need a browser or a Vercel preview. |
| 5 | chat stream | Not run (no session; incremental delivery needs a live stream). |
| 6 | cold start | Not run: needs stopping the backend, which is not ours to stop; Render sleep needs a deployed instance. |
| 7 (partial) | logout works without a valid access token | App logout with a bogus RT: 200 `{"sent":true}`, cookies cleared. Backend `/auth/logout` with a tampered token: 204. Matches. **Not run:** after expiring the access token and logging out, replaying the old RT fails (needs a real session). |

### Second attempt: 2026-10-20, slug `local-dev`

`POST /auth/login` directly on the backend with slug `local-dev` and the `TEST_EMAIL`/`TEST_PASSWORD` pair answers **401 `Invalid credentials`** (and 401 `invalid_credentials` through the BFF). The backend cannot tell a wrong slug, a wrong email and a wrong password apart, so one of the three does not match the account. Nothing else was tried (login is limited to 5 attempts per 60 s per account). Every authenticated step stays **not run**: login, documents and chat through the BFF, refresh rotation, replay of an old refresh token, logout after the access token expired, the 4 MB upload through the dev server.

Planned way to expire the access token without waiting: send the request with only the `hh_rt` cookie (exactly what deleting `hh_at` in DevTools does). A genuinely expired-but-present JWT cannot be made without the signing key, so that variant is not covered. The 4 MB upload through the dev server does not test Vercel's 4.5 MB limit.

## Observed run 3: 2026-10-20 (authenticated, terminal only)

Setup: slug from `TEST_TENANT_SLUG`, credentials from the shell (never printed). Own dev server on port 3100, `BACKEND_URL` from the shell. Backend not modified. Driven by a script with `curl`-equivalent requests, so **browser behaviour is not covered**. The "expire the access token" step is done by sending only `hh_rt` (same as deleting `hh_at`).

| Step | Expected | Observed |
|---|---|---|
| 1.2 | login 200 `{"ok":true}` | 200 `{"ok":true}`, no tokens in the body. Matches. |
| 1.3 | HttpOnly, SameSite=Lax, Path `/`, not Secure; `hh_at` = token lifetime (default 15 min), `hh_rt` ~7 days | HttpOnly, SameSite=lax, Path `/`, no Secure. `hh_rt` Max-Age 604800 (7 days). `hh_at` Max-Age 3599 (~1 h): the backend's access-token default is 15 minutes, but the local app overrides it to 60 minutes (verified exp minus iat = 3600 s), and the cookie lifetime follows the token. Not a defect. |
| 1.4 | wrong password, no cookies | 401 `invalid_credentials`, 0 cookies. Matches. |
| 2.2 | no `hh_at`: 401 `token_expired`, refresh, retry | `GET /api/documents` with only `hh_rt`: 401 `{"code":"token_expired"}`. `POST /api/auth/refresh` 200 `{"ok":true}`. The browser-side retry is not run (needs a browser). |
| 2.3 | `hh_rt` changes, `hh_at` returns | Both set; `hh_rt` differs from RT-A. Matches. `GET /api/documents` with the new `hh_at`: 200. |
| 2.4-2.6 | no token text in logs; one refresh across tabs | No `eyJ` in the dev server log. Parallel tabs and Web Lock: not run (browser). |
| 3.2 | replay spent RT-A: 401, cookies cleared | 401 `{"code":"session_expired"}`, `hh_at` and `hh_rt` cleared (`Max-Age=0`). Backend "refresh token reuse" log and `forced_logout` line not checked (no access to the backend log). |
| 3.3 | RT-B (current) rejected after the reuse | `POST /api/auth/refresh` with RT-B: 401 `session_expired`. **The family is revoked.** The redirect and no-loop part needs a browser: not run. |
| 3.4 | bad or missing Origin gives 403 | Both 403 `{"code":"bad_origin"}`. Matches. |
| Documents list | 200 | 200, an empty list for this tenant. |
| 4.1 | 4 MiB text accepted | **Not accepted: 413 `{"detail":"Document is too large"}`.** A 4 MiB (and 4 MiB + 1) random-text `.txt` is under the 5 MiB file limit but its extracted text exceeds `max_document_chars` (500 000), so the backend refuses it. A 6 MiB file gives 413 `Request body is too large`. The checklist's text-file recipe cannot work; use a PDF. |
| 4.1 (PDF) | upload accepted, PENDING then READY | A valid 4 194 304-byte PDF (one short text line plus padding): `POST /api/documents/upload` 201 in 2.2 s, status READY at once (still READY after 5 s). **This goes through my dev server only and does NOT test Vercel's 4.5 MB function limit**, which exists only on Vercel: not run. |
| 4.2 | over 4 MB rejected in the browser | Not run (browser). |
| 4.4 | delete 204 | `DELETE /api/documents/<id>` 204. The confirm dialog is not run (browser). |
| 5.1 | `POST /api/chat/stream` 200 `text/event-stream`, incremental, sources | 200 `text/event-stream; charset=utf-8`. 15 chunks arrived over 0.85 s (not one block). Events: `token` x15, `sources`, `done` (`status: complete`). Visible UI incrementality is not run (browser). **Finding:** the answer contained the marker `【1】` (fullwidth brackets) while `done.cited` was `[]`, so no source chips would show. The client's `[n]` parsing was not exercised against this: check it. |
| 5.2-5.6 | refusal, `conversation_id`, rate limit, embedding failure, expired token mid-chat | Not run: not attempted to avoid extra provider calls and the 10 per 60 s limit. |
| 6 | cold start | Not run: needs the backend stopped or a sleeping Render instance. |
| 7 | logout with only `hh_rt`, then replay | `POST /api/auth/logout` with only `hh_rt` (no `hh_at`): 200 `{"sent":true}`, both cookies cleared. Replaying that never-rotated RT on `/api/auth/refresh`: **401 `session_expired`**, so the backend revoked it. Note the old `hh_at` still returned 200 on `GET /api/documents` afterwards (access JWTs are stateless until they expire). |
