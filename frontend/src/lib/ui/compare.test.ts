import { expect, test } from "vitest";
import { canRevealNext, compareIntro, snippet, uniqueDocumentIds, type SearchHit } from "./compare";

const hit = (document_id: string): SearchHit => ({
  char_end: 1, char_start: 0, chunk_id: `c-${document_id}`, chunk_index: 0, content: "x",
  document_id, document_title: document_id, found_by: ["vector"], keyword_rank: null,
  rrf_score: 0, score: null, vector_rank: null,
});

test("marks documents present in exactly one list", () => {
  const u = uniqueDocumentIds({ vector: [hit("a"), hit("b")], keyword: [hit("b"), hit("c")], hybrid: [hit("b")] });
  expect([...u.get("vector")!]).toEqual(["a"]);
  expect([...u.get("keyword")!]).toEqual(["c"]);
  expect([...u.get("hybrid")!]).toEqual([]);
});

test("a failed list does not make the others look unique; a single list marks nothing", () => {
  const u = uniqueDocumentIds({ vector: [hit("a")] });
  expect([...u.get("vector")!]).toEqual([]);
});

test("snippet collapses whitespace and truncates", () => {
  expect(snippet("a\n\n  b")).toBe("a b");
  expect(snippet("x".repeat(500))).toHaveLength(161);
});

test("whyListed reads the ranks, names a single branch only in the hybrid column, and admits a missing rank", async () => {
  const { whyListed } = await import("./compare");
  const h = (v: number | null, k: number | null): SearchHit => ({ ...hit("a"), vector_rank: v, keyword_rank: k });
  expect(whyListed(h(3, 1), "hybrid")).toBe("Vector rank 3 · Keyword rank 1");
  expect(whyListed(h(4, null), "hybrid")).toBe("Found by vector only (rank 4)");
  expect(whyListed(h(null, 2), "hybrid")).toBe("Found by keyword only (rank 2)");
  expect(whyListed(h(4, null), "vector")).toBe("Vector rank 4");
  expect(whyListed(h(null, 2), "keyword")).toBe("Keyword rank 2");
  expect(whyListed(h(null, null), "hybrid")).toBe("No rank was reported for this passage");
});

test("canRevealNext: first column and errors go at once; a finished column waits for the step", () => {
  expect(canRevealNext(0, ["done", "pending", "pending"], false)).toBe(true);
  expect(canRevealNext(0, ["pending", "done", "done"], false)).toBe(false);
  expect(canRevealNext(1, ["done", "done", "done"], false)).toBe(false);
  expect(canRevealNext(1, ["done", "done", "done"], true)).toBe(true);
  expect(canRevealNext(1, ["done", "error", "done"], false)).toBe(true);
  expect(canRevealNext(2, ["done", "error", "done"], false)).toBe(true); // an error adds no step
  expect(canRevealNext(2, ["done", "done", "pending"], true)).toBe(false);
  expect(canRevealNext(3, ["done", "done", "done"], true)).toBe(false);
});

test("compareIntro quotes the query verbatim", () => {
  expect(compareIntro("<b>x</b>")).toBe("Comparing Vector, Keyword and Hybrid for \u201c<b>x</b>\u201d.");
});
