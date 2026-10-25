import type { components } from "@/lib/api/schema";

export type SearchHit = components["schemas"]["SearchHitRead"];
export type SearchMode = components["schemas"]["SearchRequest"]["mode"];

export const MODES: readonly { mode: SearchMode; label: string }[] = [
  { mode: "vector", label: "Vector" },
  { mode: "keyword", label: "Keyword" },
  { mode: "hybrid", label: "Hybrid" },
];

const SNIPPET_CHARS = 160;

export function snippet(content: string): string {
  const flat = content.replace(/\s+/g, " ").trim();
  return flat.length > SNIPPET_CHARS ? `${flat.slice(0, SNIPPET_CHARS).trimEnd()}…` : flat;
}

/**
 * Document ids that appear in exactly one of the loaded lists. With fewer than two loaded
 * lists there is nothing to compare, so nothing is marked.
 */
export function uniqueDocumentIds(lists: Partial<Record<SearchMode, SearchHit[]>>): Map<SearchMode, Set<string>> {
  const loaded = (Object.entries(lists) as [SearchMode, SearchHit[]][]).filter(([, hits]) => hits !== undefined);
  const out = new Map<SearchMode, Set<string>>(loaded.map(([m]) => [m, new Set<string>()]));
  if (loaded.length < 2) return out;
  const seenIn = new Map<string, Set<SearchMode>>();
  for (const [mode, hits] of loaded) {
    for (const h of hits) seenIn.set(h.document_id, (seenIn.get(h.document_id) ?? new Set()).add(mode));
  }
  for (const [mode, hits] of loaded) {
    for (const h of hits) if (seenIn.get(h.document_id)?.size === 1) out.get(mode)?.add(h.document_id);
  }
  return out;
}
