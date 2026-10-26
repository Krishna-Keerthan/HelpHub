/**
 * The only two things the browser keeps across a refresh (decisions.md D15): the current chat
 * conversation id (a UUID) and the last submitted Compare query. Both live in sessionStorage, which is
 * per tab. Every access is wrapped: with storage blocked the app works, it just forgets on refresh.
 */
export const CONVERSATION_STORAGE = "hh_conversation";
export const COMPARE_QUERY_STORAGE = "hh_compare_query";

export function readStored(name: string): string | null {
  try {
    return sessionStorage.getItem(name);
  } catch {
    return null;
  }
}

export function writeStored(name: string, value: string): void {
  try {
    sessionStorage.setItem(name, value);
  } catch {
    // storage blocked or full: nothing to restore later
  }
}

export function clearStored(name: string): void {
  try {
    sessionStorage.removeItem(name);
  } catch {
    // storage blocked
  }
}
