/**
 * Browser side of token refresh. Backend rotates the refresh token on every use and
 * revokes the whole family if a used token comes back, so two refreshes must never run
 * at once for one cookie jar:
 *  - same tab: callers share one in-flight promise;
 *  - other tabs (same cookie jar): serialised by a Web Lock; a caller whose request was
 *    sent before the latest refresh finished adopts that result instead of refreshing;
 *  - server instances need no coordination, they only ever see one request per rotation.
 */
export type RefreshOutcome = "ok" | "expired" | "waking" | "indeterminate";

export type SessionDeps = {
  post: () => Promise<Response>;
  now: () => number;
  sleep: (ms: number) => Promise<void>;
  withLock: <T>(fn: () => Promise<T>) => Promise<T>;
  readStamp: () => number;
  writeStamp: (ms: number) => void;
};

const STAMP_KEY = "hh_refreshed_at";
const LOCK_NAME = "hh-refresh";

export const browserDeps: SessionDeps = {
  post: () =>
    fetch("/api/auth/refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }),
  now: () => Date.now(),
  sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
  withLock: (fn) =>
    typeof navigator !== "undefined" && navigator.locks
      ? navigator.locks.request(LOCK_NAME, fn)
      : fn(),
  readStamp: () => {
    try {
      return Number(localStorage.getItem(STAMP_KEY)) || 0;
    } catch {
      return 0;
    }
  },
  writeStamp: (ms) => {
    try {
      localStorage.setItem(STAMP_KEY, String(ms));
    } catch {
      // storage unavailable: other tabs just refresh again, serialised by the lock
    }
  },
};

let inflight: Promise<RefreshOutcome> | null = null;

async function refreshOnce(sentAt: number, d: SessionDeps): Promise<RefreshOutcome> {
  return d.withLock(async () => {
    if (d.readStamp() > sentAt) return "ok"; // another tab already rotated after this request was sent
    let res: Response;
    try {
      res = await d.post();
    } catch {
      return "waking"; // request never reached the server: nothing was spent
    }
    if (res.ok) {
      d.writeStamp(d.now());
      return "ok";
    }
    if (res.status === 401) return "expired";
    if (res.status === 503) return "waking";
    return "indeterminate";
  });
}

/** Refresh the session once (single-flight). `sentAt` is when the failed request was sent. */
export function refreshSession(sentAt: number, d: SessionDeps = browserDeps): Promise<RefreshOutcome> {
  inflight ??= refreshOnce(sentAt, d).finally(() => {
    inflight = null;
  });
  return inflight;
}

export const WAKING_RETRIES = 2;
export const WAKING_DELAY_MS = 3_000;

/**
 * Refresh, retrying only the "waking" outcome (token not spent, so a resend is safe).
 * "indeterminate" is never retried automatically: the token may already be rotated.
 * `onWaking` lets the UI show a "service waking up" state.
 */
export async function refreshWithBackoff(
  sentAt: number,
  onWaking: (waking: boolean) => void = () => {},
  d: SessionDeps = browserDeps,
): Promise<RefreshOutcome> {
  let outcome = await refreshSession(sentAt, d);
  for (let i = 0; outcome === "waking" && i < WAKING_RETRIES; i++) {
    onWaking(true);
    await d.sleep(WAKING_DELAY_MS * (i + 1));
    outcome = await refreshSession(sentAt, d);
  }
  onWaking(outcome === "waking");
  return outcome;
}

/** Test helper: forget any in-flight refresh. */
export function resetSessionForTests(): void {
  inflight = null;
}
