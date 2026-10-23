import { expect, test } from "vitest";
import { displayCitations } from "./citation-display";

test("lenticular and fullwidth markers become ASCII", () => {
  expect(displayCitations("Free up space【2】 and retry［10］.")).toBe("Free up space[2] and retry[10].");
});

test("fullwidth digits inside the marker are converted too", () => {
  expect(displayCitations("see 【１２】")).toBe("see [12]");
});

test("ASCII markers and other brackets are left alone", () => {
  const s = "a [1] b 【note】 c ［x］ d 【】 e 【1";
  expect(displayCitations(s)).toBe(s);
});

test("text without markers is unchanged", () => {
  expect(displayCitations("plain **text**\n\n* item")).toBe("plain **text**\n\n* item");
});
