import { NextResponse, type NextRequest } from "next/server";
import { ACCESS_COOKIE, readCookie } from "./cookies";
import { isExpired } from "./jwt";
import { forbiddenOrigin, originAllowed } from "./origin";
import { backendUrl, fetchWithHeaderTimeout, realDeps, wakeBackend, type Deps } from "./upstream";

/** Backend path prefixes the browser may reach through the BFF. Auth routes have their own handlers. */
const ALLOWED = ["documents", "conversations", "chat", "search", "users", "auth/me"];
const HEADER_TIMEOUT_MS = 90_000;
// Allow-list. Never copy content-length, content-encoding or transfer-encoding: fetch() has already
// decoded the body, so they describe bytes we no longer have. The runtime computes them.
const COPY_RESPONSE_HEADERS = ["content-type", "retry-after", "content-disposition"];

export const tokenExpired = () => NextResponse.json({ code: "token_expired" }, { status: 401 });

/**
 * Forward an authenticated request to FastAPI with the access token from the cookie.
 * It never refreshes: a missing, expired or upstream-rejected access token is answered
 * `401 {code:"token_expired"}` and the browser refreshes once under its Web Lock.
 */
export async function passthrough(
  req: NextRequest,
  segments: string[],
  deps: Deps = realDeps,
): Promise<Response> {
  const path = segments.join("/");
  if (!ALLOWED.some((p) => path === p || path.startsWith(`${p}/`))) {
    return NextResponse.json({ code: "not_found" }, { status: 404 });
  }
  if (!originAllowed(req)) return forbiddenOrigin();

  const at = readCookie(req.cookies, ACCESS_COOKIE);
  if (!at || isExpired(at, Date.now())) return tokenExpired();

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const headers = new Headers({ Authorization: `Bearer ${at}` });
  for (const name of ["content-type", "accept", "content-length"]) {
    const v = req.headers.get(name);
    if (v) headers.set(name, v);
  }
  const url = `${backendUrl()}/${path}${req.nextUrl.search}`;
  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers,
    signal: req.signal,
    ...(hasBody ? { body: req.body, duplex: "half" } : {}),
  };

  const unavailable = () =>
    NextResponse.json({ code: "service_waking" }, { status: 503, headers: { "Retry-After": "5" } });

  let upstream: Response;
  try {
    upstream = await fetchWithHeaderTimeout(deps, url, init, HEADER_TIMEOUT_MS);
  } catch {
    // A body was already streamed, so only body-less (idempotent) requests are retried.
    if (hasBody || req.signal.aborted || !(await wakeBackend(deps))) return unavailable();
    try {
      upstream = await fetchWithHeaderTimeout(deps, url, init, HEADER_TIMEOUT_MS);
    } catch {
      return unavailable();
    }
  }
  if (upstream.status === 401) return tokenExpired();

  const out = new Headers();
  for (const name of COPY_RESPONSE_HEADERS) {
    const v = upstream.headers.get(name);
    if (v) out.set(name, v);
  }
  out.set("Cache-Control", "no-store, no-transform");
  out.set("X-Accel-Buffering", "no");
  return new Response(upstream.body, { status: upstream.status, headers: out });
}
