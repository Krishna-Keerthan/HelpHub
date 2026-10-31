import { expect, test } from "vitest";
import { canRevealNext, repeatNotes, snippet, topResultTakeaway, uniqueDocumentIds, type SearchHit } from "./compare";

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

// ---- column titles ----------------------------------------------------------------------------------------

// ---- takeaway ---------------------------------------------------------------------------------------------

const titled = (id: string, title: string): SearchHit => ({ ...hit(id), document_title: title });

test("takeaway: all three lists start with the same document", () => {
  const l = [titled("a", "Refund policy"), titled("b", "Other")];
  expect(topResultTakeaway({ vector: l, keyword: [titled("a", "Refund policy")], hybrid: [titled("a", "Refund policy")] })).toBe(
    "All three lists agree on the top result: \u201cRefund policy\u201d.",
  );
});

test("takeaway: the top result differs, naming each list's top document", () => {
  expect(
    topResultTakeaway({ vector: [titled("a", "A doc")], keyword: [titled("b", "B doc")], hybrid: [titled("c", "C doc")] }),
  ).toBe("The top result differs: meaning gives \u201cA doc\u201d, exact words give \u201cB doc\u201d, combined gives \u201cC doc\u201d.");
});

test("takeaway: two agreeing and one different is still reported as differing, truthfully", () => {
  const t = topResultTakeaway({ vector: [titled("a", "A doc")], keyword: [titled("b", "B doc")], hybrid: [titled("a", "A doc")] });
  expect(t).toBe("The top result differs: meaning gives \u201cA doc\u201d, exact words give \u201cB doc\u201d, combined gives \u201cA doc\u201d.");
});

test("takeaway compares document ids, not titles or passages", () => {
  // Same title on two different documents: not an agreement. Same document, different passage: agreement.
  expect(topResultTakeaway({ vector: [titled("a", "Same")], keyword: [titled("b", "Same")], hybrid: [titled("a", "Same")] })).toMatch(/differs/);
  const other = { ...titled("a", "Same"), chunk_id: "other", chunk_index: 7 };
  expect(topResultTakeaway({ vector: [titled("a", "Same")], keyword: [other], hybrid: [titled("a", "Same")] })).toMatch(/agree/);
});

test("takeaway uses only each list's first entry", () => {
  const t = topResultTakeaway({
    vector: [titled("a", "A"), titled("z", "Z")], keyword: [titled("a", "A"), titled("y", "Y")], hybrid: [titled("a", "A")],
  });
  expect(t).toMatch(/agree/);
});

test("takeaway is null unless all three lists are loaded and non-empty", () => {
  const one = [titled("a", "A")];
  expect(topResultTakeaway({})).toBeNull();
  expect(topResultTakeaway({ vector: one, keyword: one })).toBeNull();
  expect(topResultTakeaway({ vector: one, keyword: one, hybrid: [] })).toBeNull();
  expect(topResultTakeaway({ vector: [], keyword: [], hybrid: [] })).toBeNull();
});

test("takeaway never ranks the modes", () => {
  const same = topResultTakeaway({ vector: [hit("a")], keyword: [hit("a")], hybrid: [hit("a")] })!;
  const diff = topResultTakeaway({ vector: [hit("a")], keyword: [hit("b")], hybrid: [hit("c")] })!;
  for (const t of [same, diff]) expect(t).not.toMatch(/better|best|worse|worst|wins|winner|more accurate/i);
});

// ---- repeated documents -----------------------------------------------------------------------------------

test("repeatNotes: a document with two passages in one list says so on both; single ones have no note", () => {
  const hits = [
    { ...hit("a"), chunk_id: "a0", chunk_index: 0 },
    hit("b"),
    { ...hit("a"), chunk_id: "a2", chunk_index: 2 },
  ];
  expect(repeatNotes(hits)).toEqual([
    "Passage 1 of this document; 2 of its passages are in this list",
    null,
    "Passage 3 of this document; 2 of its passages are in this list",
  ]);
});

test("repeatNotes: no repeats, no notes; empty list is fine", () => {
  expect(repeatNotes([hit("a"), hit("b")])).toEqual([null, null]);
  expect(repeatNotes([])).toEqual([]);
});

// ---- display-only cleanup of leading Markdown in excerpts ---------------------------------------------------

test.each([
  ["# Title\nbody text", "Title body text"],
  ["## Refund policy\n\nFive days.", "Refund policy Five days."],
  ["###### Deep\nx", "Deep x"],
  ["#   Spaced   heading", "Spaced heading"],
  ["> quoted passage", "quoted passage"],
  ["- first item\n- second item", "first item - second item"], // only the leading marker
  ["* bullet", "bullet"],
  ["+ bullet", "bullet"],
  ["> ## Quoted heading", "Quoted heading"],
  ["  \n# After blank lines", "After blank lines"],
])("snippet strips leading Markdown noise: %j", (input, expected) => {
  expect(snippet(input)).toBe(expected);
});

test.each([
  ["#hashtag at the start", "#hashtag at the start"],
  ["#12 was the issue", "#12 was the issue"],
  ["C# is a language", "C# is a language"],
  ["See issue #12 for details", "See issue #12 for details"],
  ["Use the #hashtag mid-sentence", "Use the #hashtag mid-sentence"],
  ["Text with ## in the middle", "Text with ## in the middle"],
  ["Text\n## Later heading", "Text ## Later heading"], // not at the start: left alone
  ["####### seven hashes", "####### seven hashes"],
  ["-5 degrees", "-5 degrees"],
  ["*emphasis* start", "*emphasis* start"],
  ["**bold** start", "**bold** start"],
  ["1. numbered", "1. numbered"],
  ["Plain text", "Plain text"],
])("snippet leaves this unchanged: %j", (input, expected) => {
  expect(snippet(input)).toBe(expected);
});

test("snippet of only markers shows them rather than an empty excerpt", () => {
  expect(snippet("#")).toBe("#");
  expect(snippet("- - -")).toBe("- - -");
  expect(snippet("")).toBe("");
});

test("snippet strips the marker before truncating, so the 160 characters are real text", () => {
  const out = snippet(`## ${"x".repeat(500)}`);
  expect(out.startsWith("x")).toBe(true);
  expect(out).toHaveLength(161);
});

test("snippet does not change its input (display only)", () => {
  const original = "## Heading\nbody";
  snippet(original);
  expect(original).toBe("## Heading\nbody");
});
