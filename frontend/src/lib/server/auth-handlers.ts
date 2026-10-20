import { NextResponse, type NextRequest } from "next/server";
import {
  clearSessionCookies,
  readCookie,
  REFRESH_COOKIE,
  setSessionCookies,
} from "./cookies";
import { countEvent } from "./events";
import { forbiddenOrigin, originAllowed } from "./origin";
import {
  backendUrl,
  fetchWithHeaderTimeout,
  realDeps,
  refreshUpstream,
  wakeBackend,
  type Deps,
  type Pair,
} from "./upstream";

/**
 * The only place a refresh token is spent. The browser calls this once per rotation,
 * serialised by a Web Lock (see lib/api/session.ts). Cookies are cleared only when the
 * backend itself answers 401; a cold start, timeout or 5xx never ends the session.
 */
export async function handleRefresh(req: NextRequest, deps: Deps = realDeps): Promise<NextResponse> {
  if (!originAllowed(req)) return forbiddenOrigin() as NextResponse;
  const rt = readCookie(req.cookies, REFRESH_COOKIE);
  if (!rt) {
    countEvent("forced_logout", "no_session");
    return NextResponse.json({ code: "no_session" }, { status: 401 });
  }

  const result = await refreshUpstream(rt, deps);
  switch (result.kind) {
    case "ok": {
      const res = NextResponse.json({ ok: true });
      setSessionCookies(res, req.url, result.pair);
      return res;
    }
    case "rejected": {
      countEvent("forced_logout", "refresh_rejected");
      const res = NextResponse.json({ code: "session_expired" }, { status: 401 });
      clearSessionCookies(res, req.url);
      return res;
    }
    case "waking":
      return NextResponse.json({ code: "service_waking" }, { status: 503, headers: { "Retry-After": "5" } });
    case "indeterminate":
      countEvent("refresh_indeterminate", result.reason);
      return NextResponse.json({ code: "refresh_indeterminate" }, { status: 502 });
  }
}


export async function handleLogin(req: NextRequest, deps: Deps = realDeps): Promise<NextResponse> {
  if (!originAllowed(req)) return forbiddenOrigin() as NextResponse;
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ code: "bad_request" }, { status: 400 });
  }
  if (!(await wakeBackend(deps))) {
    return NextResponse.json({ code: "service_waking" }, { status: 503, headers: { "Retry-After": "5" } });
  }
  let res: Response;
  try {
    res = await fetchWithHeaderTimeout(
      deps,
      `${backendUrl()}/auth/login`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
      45_000,
    );
  } catch {
    return NextResponse.json({ code: "service_waking" }, { status: 503, headers: { "Retry-After": "5" } });
  }
  if (!res.ok) {
    const code = res.status === 401 ? "invalid_credentials" : res.status === 429 ? "rate_limited" : "login_failed";
    const headers: Record<string, string> = {};
    const retry = res.headers.get("Retry-After");
    if (retry) headers["Retry-After"] = retry;
    return NextResponse.json({ code }, { status: res.status === 422 ? 422 : res.status === 401 || res.status === 429 ? res.status : 502, headers });
  }
  const pair = (await res.json()) as Pair;
  const out = NextResponse.json({ ok: true });
  setSessionCookies(out, req.url, pair);
  return out;
}


/**
 * Always clears the local cookies. The backend authenticates logout by the refresh
 * token in the body (no Bearer, so it works after the access token expired) and
 * answers 204 whether or not it revoked anything; `sent` only says it acknowledged.
 */
export async function handleLogout(req: NextRequest, deps: Deps = realDeps): Promise<NextResponse> {
  if (!originAllowed(req)) return forbiddenOrigin() as NextResponse;
  const rt = readCookie(req.cookies, REFRESH_COOKIE);
  let sent = false;
  if (rt) {
    try {
      const res = await fetchWithHeaderTimeout(
        deps,
        `${backendUrl()}/auth/logout`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: rt }),
        },
        10_000,
      );
      sent = res.status === 204;
    } catch {
      sent = false;
    }
  }
  const out = NextResponse.json({ sent });
  clearSessionCookies(out, req.url);
  return out;
}
