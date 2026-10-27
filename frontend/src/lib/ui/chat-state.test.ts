import { expect, test } from "vitest";
import { chatHttpMessage, STREAM_CUT_OFF, STREAM_CUT_OFF_MESSAGE, streamErrorMessage } from "./chat-state";

test("HTTP failures get a plain-language message and never expose backend text or status codes", () => {
  const cases: [number, number | null, RegExp][] = [
    [429, 12, /Wait 12 seconds/],
    [429, null, /Wait a moment/],
    [503, null, /waking up.*about a minute/],
    [404, null, /conversation is no longer available/],
    [422, null, /between 1 and 2000 characters/],
    [403, null, /blocked for safety/],
    [500, null, /our side/],
    [418, null, /could not be sent/],
  ];
  for (const [status, retry, re] of cases) {
    const m = chatHttpMessage(status, retry);
    expect(m, String(status)).toMatch(re);
    expect(m).not.toMatch(/\b(HTTP|detail|[45]\d\d)\b/);
  }
});

// error.code values documented in docs/api/chat-stream.md.
const DOCUMENTED_CODES = [
  "llm_unavailable",
  "llm_timeout",
  "llm_rate_limited",
  "llm_bad_request",
  "llm_model_unavailable",
  "llm_empty_response",
  "embedding_unavailable",
  "internal_error",
];
const GENERIC = "Something went wrong while answering. Please try again.";

test.each(DOCUMENTED_CODES)("documented error code %s has a non-empty plain-language message", (code) => {
  const m = streamErrorMessage(code);
  expect(m.length).toBeGreaterThan(0);
  expect(m).not.toMatch(/llm_|embedding_|_/); // never the raw code
  if (code !== "internal_error") expect(m, code).not.toBe(GENERIC);
});

test("embedding_unavailable says the search service is down; unknown or missing codes are generic", () => {
  expect(streamErrorMessage("embedding_unavailable")).toBe("The search service is unavailable. Please try again later.");
  expect(streamErrorMessage("internal_error")).toBe(GENERIC);
  expect(streamErrorMessage("totally_new")).toBe(GENERIC);
  expect(streamErrorMessage(undefined)).toBe(GENERIC);
});

test("the client-side cut-off state has its own message and is not a documented backend code", () => {
  expect(streamErrorMessage(STREAM_CUT_OFF)).toBe(STREAM_CUT_OFF_MESSAGE);
  expect(DOCUMENTED_CODES).not.toContain(STREAM_CUT_OFF);
  expect(STREAM_CUT_OFF_MESSAGE).not.toBe(GENERIC);
});

import { messagesToTurns, type MessageRow } from "./chat-state";

const src = (index: number) => ({
  index, chunk_id: `c${index}`, document_id: `d${index}`, document_title: `Doc ${index}`, chunk_index: 0, score: 0.5,
});
const user = (content: string): MessageRow => ({ role: "user", content, status: "complete", sources: [] });
const bot = (content: string, status: string, sources: unknown = []): MessageRow => ({ role: "assistant", content, status, sources });

test("mapper pairs each user message with the assistant message after it and restores nextId", () => {
  const { turns, nextId } = messagesToTurns([
    user("q1"), bot("a1 [1]", "complete", [src(1), src(2)]), user("q2"), bot("a2", "complete"),
  ]);
  expect(turns.map((t) => [t.id, t.question, t.answer])).toEqual([[1, "q1", "a1 [1]"], [2, "q2", "a2"]]);
  expect(turns[0]).toMatchObject({ status: "complete", cited: [1] });
  expect(turns[0]!.sources.map((s) => s.index)).toEqual([1, 2]);
  expect(nextId).toBe(3);
});

test("mapper: every stored status maps to the live one", () => {
  const t = (status: string, content = "text") => messagesToTurns([user("q"), bot(content, status)]).turns[0]!;
  expect(t("complete")).toMatchObject({ status: "complete" });
  expect(t("no_answer")).toMatchObject({ status: "no_answer" });
  expect(t("failed").status).toBe("error");
  expect(t("failed").errorCode).toBeUndefined();
  expect(streamErrorMessage(t("failed").errorCode)).toMatch(/Something went wrong while answering\. Please try again/);
  expect(t("interrupted", "partial")).toMatchObject({ status: "error", errorCode: STREAM_CUT_OFF, answer: "partial" });
});

test("mapper: a user message with no assistant row is a cut-off turn, also in the middle", () => {
  const { turns, nextId } = messagesToTurns([user("lost"), user("q2"), bot("a2", "complete")]);
  expect(turns[0]).toMatchObject({ question: "lost", answer: "", status: "error", errorCode: STREAM_CUT_OFF });
  expect(turns[1]).toMatchObject({ question: "q2", answer: "a2", status: "complete" });
  expect(nextId).toBe(3);
});

test("mapper: an invalid source is dropped without renumbering, so the other chips keep their numbers", () => {
  const sources = [src(1), { ...src(2), score: "high" }, src(3), null, "x"];
  const [turn] = messagesToTurns([user("q"), bot("see [1] [2] [3]", "complete", sources)]).turns;
  expect(turn!.sources.map((s) => s.index)).toEqual([1, 3]);
  // cited counts against the stored list (5), as the backend does; chips are matched by index
  expect(turn!.cited).toEqual([1, 2, 3]);
});

test("mapper: sources that are not a list, and an empty history, never crash", () => {
  expect(messagesToTurns([user("q"), bot("a", "complete", "nope")]).turns[0]!.sources).toEqual([]);
  expect(messagesToTurns([])).toEqual({ turns: [], nextId: 1 });
});
