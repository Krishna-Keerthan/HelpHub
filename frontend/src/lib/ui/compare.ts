import type { components } from "@/lib/api/schema";

export type SearchHit = components["schemas"]["SearchHitRead"];
export type SearchMode = components["schemas"]["SearchRequest"]["mode"];

/**
 * `label` is the short mode name (list and button names); `title` is the column heading; `tab` is the
 * short switcher label used below lg, where one column shows at a time.
 */
export const MODES: readonly { mode: SearchMode; label: string; title: string; tab: string }[] = [
  { mode: "vector", label: "Vector", title: "Meaning (vector)", tab: "Meaning" },
  { mode: "keyword", label: "Keyword", title: "Exact words (keyword)", tab: "Exact words" },
  { mode: "hybrid", label: "Hybrid", title: "Combined (hybrid)", tab: "Combined" },
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
/** Shown once above the columns, not on every card. */
export const SIMILARITY_LEGEND = "Similarity is the cosine similarity between the question and a passage. It is only comparable within one column.";
export const RANK_HELP = "Position among the passages this search found, 1 being first.";

/** Minimum milliseconds between one column appearing and the next. */
export const REVEAL_STEP_MS = 700;

export type ColumnStatus = "pending" | "done" | "error";

/**
 * Whether the column at index `revealed` may be shown now, given that the columns before it are shown.
 * The first column and any error show as soon as they settle; a finished column also waits for the step
 * after the previous one (`cooled`), unless that previous one was an error.
 */
export function canRevealNext(revealed: number, statuses: readonly ColumnStatus[], cooled: boolean): boolean {
  const status = statuses[revealed];
  if (status === undefined || status === "pending") return false;
  if (status === "error" || revealed === 0) return true;
  return cooled || statuses[revealed - 1] === "error";
}

/** The one line shown above the columns once a query has been submitted. */
export const compareIntro = (query: string): string =>
  `Comparing Vector, Keyword and Hybrid for \u201c${query}\u201d.`;

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

/**
 * One line on whether the three lists start with the same document, from the order of each list and the
 * document ids only. It says nothing about which list is better. Null unless all three lists are loaded and
 * none is empty (there is nothing to compare otherwise).
 */
export function topResultTakeaway(lists: Partial<Record<SearchMode, SearchHit[]>>): string | null {
  const top = (m: SearchMode): SearchHit | undefined => lists[m]?.[0];
  const [vector, keyword, hybrid] = [top("vector"), top("keyword"), top("hybrid")];
  if (!vector || !keyword || !hybrid) return null;
  if (vector.document_id === keyword.document_id && keyword.document_id === hybrid.document_id) {
    return `All three lists agree on the top result: \u201c${vector.document_title}\u201d.`;
  }
  return (
    `The top result differs: meaning gives \u201c${vector.document_title}\u201d, ` +
    `exact words give \u201c${keyword.document_title}\u201d, combined gives \u201c${hybrid.document_title}\u201d.`
  );
}

/**
 * A note for each hit whose document appears more than once in the same list. Results are passages, so this
 * is two different passages (chunks) of one document, not a duplicate: say so instead of hiding either.
 */
export function repeatNotes(hits: readonly SearchHit[]): (string | null)[] {
  const counts = new Map<string, number>();
  for (const h of hits) counts.set(h.document_id, (counts.get(h.document_id) ?? 0) + 1);
  return hits.map((h) => {
    const n = counts.get(h.document_id) ?? 1;
    return n > 1 ? `Passage ${h.chunk_index + 1} of this document; ${n} of its passages are in this list` : null;
  });
}
