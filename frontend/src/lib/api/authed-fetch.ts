import { refreshWithBackoff } from "./session";

type Listener = (waking: boolean) => void;
const listeners = new Set<Listener>();

/** Subscribe to the "service waking up" state (backend cold start). Returns an unsubscribe fn. */
export function onServiceWaking(l: Listener): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}
const emitWaking = (w: boolean) => listeners.forEach((l) => l(w));

async function isTokenExpired(res: Response): Promise<boolean> {
  if (res.status !== 401) return false;
  try {
    return ((await res.clone().json()) as { code?: string }).code === "token_expired";
  } catch {
    return false;
  }
}

export type AuthedFetchDeps = {
  fetch: typeof fetch;
  refresh: typeof refreshWithBackoff;
  now: () => number;
  endSession: () => void;
};

export const defaultAuthedDeps: AuthedFetchDeps = {
  fetch: (...a) => fetch(...a),
  refresh: refreshWithBackoff,
  now: () => Date.now(),
  endSession: () => {
    const next = location.pathname + location.search;
    // Full navigation on purpose: it drops all in-memory client state.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    location.href = `/login?next=${encodeURIComponent(next)}`;
  },
};

/**
 * fetch for BFF calls. On `401 token_expired` it refreshes once and retries once; a
 * second 401 is returned as is (no loop). Only a 401 from the refresh itself ends the
 * session; a cold start yields a 503 `service_waking` response instead.
 */
export function createAuthedFetch(d: AuthedFetchDeps = defaultAuthedDeps) {
  return async (input: Request): Promise<Response> => {
    const sentAt = d.now();
    const retry = input.clone();
    const res = await d.fetch(input);
    if (!(await isTokenExpired(res))) return res;

    const outcome = await d.refresh(sentAt, emitWaking);
    if (outcome === "ok") return d.fetch(retry);
    if (outcome === "expired") {
      d.endSession();
      return res;
    }
    const code = outcome === "waking" ? "service_waking" : "refresh_indeterminate";
    return Response.json({ code }, { status: outcome === "waking" ? 503 : 502 });
  };
}

export const authedFetch = createAuthedFetch();
