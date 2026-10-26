import type { QueryClient } from "@tanstack/react-query";
import { queryKeys } from "./hooks";

/** Root of every cached Compare search (`["compare", mode, query]`). */
export const COMPARE_KEY = ["compare"] as const;

/**
 * Call after an upload or a delete: the documents list is refetched and the cached Compare results,
 * which came from the old document set, are dropped. They are removed rather than invalidated because
 * a restored Compare page seeds its columns straight from the cache without checking staleness.
 */
export function afterDocumentsChanged(client: QueryClient): Promise<void> {
  client.removeQueries({ queryKey: COMPARE_KEY });
  return client.invalidateQueries({ queryKey: queryKeys.documents });
}
