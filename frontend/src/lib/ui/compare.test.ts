import { expect, test } from "vitest";
import { snippet, uniqueDocumentIds, type SearchHit } from "./compare";

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
