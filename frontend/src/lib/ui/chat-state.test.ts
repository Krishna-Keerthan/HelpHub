import { expect, test } from "vitest";
import { chatHttpMessage, streamErrorMessage } from "./chat-state";

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

test("every documented in-stream error code has its own message; unknown codes fall back", () => {
  const codes = [
    "llm_unavailable", "llm_timeout", "llm_rate_limited", "llm_bad_request",
    "llm_model_unavailable", "llm_empty_response", "embedding_unavailable", "interrupted",
  ];
  const generic = streamErrorMessage("internal_error");
  expect(generic).toMatch(/Something went wrong/);
  for (const c of codes) expect(streamErrorMessage(c), c).not.toBe(generic);
  expect(streamErrorMessage(undefined)).toBe(generic);
  expect(streamErrorMessage("totally_new")).toBe(generic);
});
