import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { DEMO_QUERIES } from "./demo-queries";

describe("DEMO_QUERIES", () => {
  it("matches the question text in docs/demo/queries.json, in order, with nothing else", () => {
    const raw = readFileSync(resolve(__dirname, "../../../docs/demo/queries.json"), "utf8");
    const questions = (JSON.parse(raw) as { queries: { query: string }[] }).queries.map((q) => q.query);
    expect(DEMO_QUERIES).toEqual(questions);
    for (const q of DEMO_QUERIES) expect(typeof q).toBe("string");
  });
});
