import { QueryClient } from "@tanstack/react-query";

/**
 * In-memory client cache for authenticated GET data (documents list, current user) and the Compare
 * search results. The cache itself is never persisted: no localStorage or IndexedDB, and a hard reload
 * starts it empty. Separately, `lib/session/storage.ts` keeps two small sessionStorage entries so a
 * refresh can restore the page: the chat conversation id and the last Compare query. Answers, passages
 * and chat messages are never written to the browser (decisions.md D15). Everything is cleared by
 * `endSessionState` (lib/session/end.ts), which calls `resetSessionCache` below, on login, logout and
 * session expiry.
 */

/** How long the documents list counts as fresh. A choice, not a measurement (decisions.md D13). */
export const DOCUMENTS_STALE_MS = 60_000;
/** How long a role answer is trusted before it is re-checked. Never longer than the session. */
export const ME_STALE_MS = 5 * 60_000;

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      // authedFetch already retries a cold start; a failed query shows its error and "Try again".
      queries: { retry: false },
    },
  });
}

let browserClient: QueryClient | undefined;

/** One client per browser tab; a fresh one per call on the server so nothing is shared between users. */
export function getQueryClient(): QueryClient {
  if (typeof window === "undefined") return makeQueryClient();
  return (browserClient ??= makeQueryClient());
}

/**
 * Forget everything cached and discard in-flight results, so one session's role or documents can
 * never show up in the next. Called on login and logout.
 */
export function resetSessionCache(): void {
  if (!browserClient) return;
  void browserClient.cancelQueries();
  browserClient.clear();
}
