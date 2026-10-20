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
3. Cookies: `hh_at` and `hh_rt` both `HttpOnly`, `SameSite=Lax`, Path `/`, **not** `Secure` (http localhost). `hh_at` expiry ~15 min, `hh_rt` ~7 days.
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
Click **Log out**. Expected: `POST /api/auth/logout` 200 `{"revoked":true}`, cookies cleared, landing on `/login`; replaying the old RT via curl as in 3.2 returns 401. If `hh_at` was already expired, `revoked` is `false` (best effort; the backend needs a valid access token) - note it.
