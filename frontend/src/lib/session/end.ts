import { resetSessionCache } from "@/lib/query/client";
import { clearStored, COMPARE_QUERY_STORAGE, CONVERSATION_STORAGE } from "./storage";

/**
 * Forget everything one session left in this tab: the query cache and the two sessionStorage entries.
 * Called on login, demo login, logout and before the redirect when a session expires, so the next user
 * of the tab never sees the previous one's conversation or comparison.
 */
export function endSessionState(): void {
  resetSessionCache();
  clearStored(CONVERSATION_STORAGE);
  clearStored(COMPARE_QUERY_STORAGE);
}
