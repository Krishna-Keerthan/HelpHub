import { QueryClient } from "@tanstack/react-query";

/**
 * In-memory client cache for authenticated GET data (documents list, current user).
 * Nothing here is persisted: no localStorage, sessionStorage or IndexedDB, so a hard reload
 * refetches by design. The cache is cleared on login and logout (see `resetSessionCache`);
 * a session that ends on its own does a full page navigation, which drops memory too.
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
