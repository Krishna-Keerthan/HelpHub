import type { components } from "@/lib/api/schema";

export type SearchHit = components["schemas"]["SearchHitRead"];
export type SearchMode = components["schemas"]["SearchRequest"]["mode"];

export const MODES: readonly { mode: SearchMode; label: string }[] = [
  { mode: "vector", label: "Vector" },
  { mode: "keyword", label: "Keyword" },
  { mode: "hybrid", label: "Hybrid" },
];

/** One-line captions shown when a column is revealed. */
export function columnCaption(mode: SearchMode): string {
  switch (mode) {
    case "vector":
      return "Passages whose meaning is closest to the question.";
    case "keyword":
      return "Passages that contain the question's words or codes.";
    case "hybrid":
      return "The vector and keyword rankings merged into one list.";
  }
}
export const RANK_ONLY_NOTE = "The API returns no keyword score, only the rank.";
export const HYBRID_NOTE = "The order combines the two ranks, which is why the similarity values are not descending.";
export const SIMILARITY_HELP = "Cosine similarity between the question and this passage. Only comparable within one column.";
export const RANK_HELP = "Position among the passages this search found, 1 being first.";

/** Milliseconds between one column appearing and the next. */
export const REVEAL_STEP_MS = 700;

/** Whether the similarity value is shown in a column: vector and hybrid only. */
export const showsSimilarity = (mode: SearchMode): boolean => mode !== "keyword";

/**
 * Why a passage is in this list, from its ranks (not from `found_by`). In the hybrid column a passage
 * found by one branch says so; in a single-mode column the mode is already the column heading.
 */
export function whyListed(hit: SearchHit, mode: SearchMode): string {
  const v = hit.vector_rank;
  const k = hit.keyword_rank;
  if (v !== null && k !== null) return `Vector rank ${v} · Keyword rank ${k}`;
  if (v !== null) return mode === "hybrid" ? `Found by vector only (rank ${v})` : `Vector rank ${v}`;
  if (k !== null) return mode === "hybrid" ? `Found by keyword only (rank ${k})` : `Keyword rank ${k}`;
  return "No rank was reported for this passage";
}

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
