/** Calls from the Next.js server to FastAPI. Never logs tokens, bodies or driver messages. */

export type Pair = { access_token: string; refresh_token: string };

export type Deps = {
  fetch: typeof fetch;
  sleep: (ms: number) => Promise<void>;
};

export const realDeps: Deps = {
  fetch: (...args) => fetch(...args),
  sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
};

export function backendUrl(): string {
  const url = process.env.BACKEND_URL;
  if (!url) throw new Error("BACKEND_URL is not set");
  return url.replace(/\/+$/, "");
}

/** fetch with a timeout that covers only the time until response headers arrive. */
export async function fetchWithHeaderTimeout(
  deps: Deps,
  url: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const ctl = new AbortController();
  const outer = init.signal;
  const onAbort = () => ctl.abort();
  outer?.addEventListener("abort", onAbort, { once: true });
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    return await deps.fetch(url, { ...init, signal: ctl.signal });
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener("abort", onAbort);
  }
}

export const WAKE = { attempts: 4, timeoutMs: 25_000, delayMs: 2_000 };

/**
 * Wake a sleeping backend (Render free spins down; spin-up takes about a minute) with
 * GET /health, which is safe to repeat. True once it answers 2xx.
 */
export async function wakeBackend(deps: Deps = realDeps, opts = WAKE): Promise<boolean> {
  for (let i = 0; i < opts.attempts; i++) {
    try {
      const res = await fetchWithHeaderTimeout(
        deps,
        `${backendUrl()}/health`,
        { method: "GET" },
        opts.timeoutMs,
      );
      if (res.ok) return true;
    } catch {
      // network error or timeout: not up yet
    }
    if (i < opts.attempts - 1) await deps.sleep(opts.delayMs);
  }
  return false;
}

export type RefreshResult =
  | { kind: "ok"; pair: Pair }
  /** The backend answered 401: the token is invalid, used, revoked or expired. */
  | { kind: "rejected" }
  /** Backend not reachable; the refresh token was NOT sent, so the session is untouched and retry is safe. */
  | { kind: "waking" }
  /** The token was sent but no usable answer came back; it may already be rotated. Do NOT resend it. */
  | { kind: "indeterminate" };

const REFRESH_TIMEOUT_MS = 45_000;

/**
 * Spend one refresh token. The token is sent at most once per call: the wake-up
 * (repeatable GET /health) happens first, so a cold start never causes a resend that
 * would look like token reuse to the backend.
 */
export async function refreshUpstream(
  refreshToken: string,
  deps: Deps = realDeps,
): Promise<RefreshResult> {
  if (!(await wakeBackend(deps))) return { kind: "waking" };
  let res: Response;
  try {
    res = await fetchWithHeaderTimeout(
      deps,
      `${backendUrl()}/auth/refresh`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      },
      REFRESH_TIMEOUT_MS,
    );
  } catch {
    return { kind: "indeterminate" };
  }
  if (res.status === 401) return { kind: "rejected" };
  if (!res.ok) return { kind: "indeterminate" };
  try {
    const pair = (await res.json()) as Partial<Pair>;
    if (typeof pair.access_token === "string" && typeof pair.refresh_token === "string") {
      return { kind: "ok", pair: { access_token: pair.access_token, refresh_token: pair.refresh_token } };
    }
  } catch {
    // fall through
  }
  return { kind: "indeterminate" };
}
