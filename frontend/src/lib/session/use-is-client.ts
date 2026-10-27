import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * False on the server and during hydration, true afterwards. Views that restore from sessionStorage mount
 * only once this is true, so their first render can read storage without a server/client mismatch.
 */
export function useIsClient(): boolean {
  return useSyncExternalStore(subscribe, () => true, () => false);
}
