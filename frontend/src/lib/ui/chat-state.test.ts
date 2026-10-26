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
