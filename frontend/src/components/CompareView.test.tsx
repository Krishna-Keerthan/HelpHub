import { fireEvent, screen, waitFor} from "@testing-library/react";
import { render } from "@/test/render";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { routeFetch } from "@/test/fetch-mock";
import { CompareView } from "./CompareView";

const hit = (doc: string, over: Record<string, unknown> = {}) => ({
  char_end: 10, char_start: 0, chunk_id: `chunk-${doc}-${Math.random()}`, chunk_index: 0,
  content: `Snippet of ${doc}`, document_id: doc, document_title: `Title ${doc}`,
  found_by: ["vector"], keyword_rank: null, rrf_score: 0.1, score: 0.5, vector_rank: 1, ...over,
});

const motion = (reduce: boolean) =>
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: reduce && q.includes("reduce"), media: q }));

// The staged reveal is covered at the end; every other test runs with reduced motion (all at once).
beforeEach(() => motion(true));
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function search(q = "refunds") {
  fireEvent.change(screen.getByLabelText("Search query"), { target: { value: q } });
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
}

const byMode = (handlers: Record<string, () => Response>) => async (req: Request) => {
  const { mode } = (await req.json()) as { mode: string };
  return handlers[mode]!();
};

test("sends three parallel requests, one per mode, with the query", async () => {
  const bodies: { query: string; mode: string }[] = [];
  routeFetch({
    "POST /api/search": async (req) => {
      bodies.push(await req.clone().json());
      return Response.json([]);
    },
  });
  render(<CompareView />);
  await search("refunds");
  await waitFor(() => expect(bodies).toHaveLength(3));
  expect(bodies.map((b) => b.mode).sort()).toEqual(["hybrid", "keyword", "vector"]);
  expect(bodies.every((b) => b.query === "refunds")).toBe(true);
  expect(await screen.findAllByText("No results.")).toHaveLength(3);
});

test("429 on one column shows the Retry-After message while others still render; retry re-runs only that mode", async () => {
  let keywordCalls = 0;
  const f = routeFetch({
    "POST /api/search": byMode({
      vector: () => Response.json([hit("a")]),
      keyword: () =>
        ++keywordCalls === 1
          ? new Response("{}", { status: 429, headers: { "Retry-After": "12" } })
          : Response.json([hit("k")]),
      hybrid: () => Response.json([hit("a")]),
    }),
  });
  render(<CompareView />);
  await search();
  expect(await screen.findByRole("alert")).toHaveTextContent("Try again in 12 seconds");
  expect(await screen.findByRole("list", { name: "Vector results" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry Keyword" }));
  expect(await screen.findByRole("list", { name: "Keyword results" })).toBeInTheDocument();
  expect(f.calls.filter((c) => c.key === "POST /api/search")).toHaveLength(4);
});

test("a network failure is a per-column error, not a crash", async () => {
  routeFetch({
    "POST /api/search": byMode({
      vector: () => { throw new TypeError("offline"); },
      keyword: () => Response.json([]),
      hybrid: () => Response.json([]),
    }),
  });
  render(<CompareView />);
  await search();
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the service");
  expect(await screen.findAllByText("No results.")).toHaveLength(2);
});

// ---- Phase 3: copy, why-listed line, staged reveal -------------------------------------------------

// Column headings are "Meaning (vector)" etc.; the short names below are only the labels used in assertions.
// Each mode answers only when its gate is opened, so a test controls the order of the responses.
// Responses arrive Hybrid, then Keyword, then Vector; returns what was visible after each.
// ---- Batch E: titles, takeaway, repeated passages, phone switcher ----------------------------------------------

test("takeaway waits for all three columns while one is still searching", async () => {
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  routeFetch({
    "POST /api/search": async (req) => {
      const { mode } = (await req.json()) as { mode: string };
      if (mode === "hybrid") await gate;
      return Response.json([hit("a")]);
    },
  });
  render(<CompareView />);
  await search();
  await screen.findByRole("list", { name: "Keyword results" });
  expect(screen.queryByText(/top result/)).toBeNull();
  release();
  expect(await screen.findByText(/All three lists agree/)).toBeInTheDocument();
});

