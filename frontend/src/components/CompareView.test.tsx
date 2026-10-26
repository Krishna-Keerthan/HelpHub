import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { routeFetch } from "@/test/fetch-mock";
import { DEMO_QUERIES } from "@/lib/demo-queries";
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

test("shows position, title, snippet; similarity only in vector and hybrid; marks unique documents", async () => {
  routeFetch({
    "POST /api/search": byMode({
      vector: () => Response.json([hit("a", { score: 0.8123 }), hit("b", { score: 0.5 })]),
      keyword: () => Response.json([hit("b", { score: null }), hit("c", { score: null })]),
      hybrid: () => Response.json([hit("b", { score: 0.3 })]),
    }),
  });
  render(<CompareView />);
  await search();
  const vector = await screen.findByRole("list", { name: "Vector results" });
  const keyword = await screen.findByRole("list", { name: "Keyword results" });
  await waitFor(() => expect(within(vector).getByText("Only in this list")).toBeInTheDocument());
  const [first, second] = within(vector).getAllByRole("listitem") as [HTMLElement, HTMLElement];
  expect(first).toHaveTextContent("#1");
  expect(first).toHaveTextContent("Title a");
  expect(first).toHaveTextContent("Snippet of a");
  expect(first).toHaveTextContent("Similarity 0.812");
  expect(first).toHaveTextContent("Only in this list");
  expect(second).not.toHaveTextContent("Only in this list");
  expect(keyword).not.toHaveTextContent("Similarity");
  expect(within(keyword).getAllByText("Only in this list")).toHaveLength(1);
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

test("columns are labelled and show a loading state while pending", async () => {
  routeFetch({ "POST /api/search": () => new Promise<Response>(() => {}) });
  render(<CompareView />);
  await search();
  for (const name of ["Vector", "Keyword", "Hybrid"]) {
    expect(screen.getByRole("region", { name })).toHaveTextContent("Searching…");
  }
});

test("a suggestion chip runs the comparison", async () => {
  const bodies: { query: string }[] = [];
  routeFetch({ "POST /api/search": async (req) => { bodies.push(await req.clone().json()); return Response.json([]); } });
  render(<CompareView />);
  fireEvent.click(screen.getByRole("button", { name: DEMO_QUERIES[0] }));
  await waitFor(() => expect(bodies).toHaveLength(3));
  expect(bodies[0]!.query).toBe(DEMO_QUERIES[0]);
  expect(screen.getByLabelText("Search query")).toHaveValue(DEMO_QUERIES[0]);
});

test("an empty query sends nothing", () => {
  const f = routeFetch({});
  render(<CompareView />);
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
  expect(f.calls).toHaveLength(0);
});

const markerCount = () => screen.queryAllByText("Only in this list").length;

test("no marker while a column is still loading", async () => {
  routeFetch({
    "POST /api/search": byMode({
      vector: () => Response.json([hit("a")]),
      keyword: () => Response.json([hit("b")]),
      hybrid: () => new Promise<Response>(() => {}) as unknown as Response, // never settles
    }),
  });
  render(<CompareView />);
  await search();
  await screen.findByRole("list", { name: "Vector results" });
  await screen.findByRole("list", { name: "Keyword results" });
  expect(screen.getByRole("region", { name: "Hybrid" })).toHaveTextContent("Searching…");
  expect(markerCount()).toBe(0);
});

test("no marker while a column has errored", async () => {
  routeFetch({
    "POST /api/search": byMode({
      vector: () => Response.json([hit("a")]),
      keyword: () => Response.json([hit("b")]),
      hybrid: () => new Response("{}", { status: 500 }),
    }),
  });
  render(<CompareView />);
  await search();
  await screen.findByRole("alert");
  await screen.findByRole("list", { name: "Keyword results" });
  expect(markerCount()).toBe(0);
});

test("markers appear once all three columns have loaded", async () => {
  routeFetch({
    "POST /api/search": byMode({
      vector: () => Response.json([hit("a")]),
      keyword: () => Response.json([hit("b")]),
      hybrid: () => Response.json([hit("b")]),
    }),
  });
  render(<CompareView />);
  await search();
  await waitFor(() => expect(markerCount()).toBe(1));
  expect(within(screen.getByRole("list", { name: "Vector results" })).getByText("Only in this list")).toBeInTheDocument();
});

// ---- Phase 3: copy, why-listed line, staged reveal -------------------------------------------------

const both = (doc: string, v: number, k: number, score = 0.4) =>
  hit(doc, { vector_rank: v, keyword_rank: k, found_by: ["vector", "keyword"], score });

test("an intro names what Vector, Keyword and Hybrid each do, in terms of passages, without ranking the modes", async () => {
  routeFetch({});
  render(<CompareView />);
  const intro = screen.getByText(/Each column shows the passages/);
  expect(intro).toHaveTextContent(/Vector compares meaning/);
  expect(intro).toHaveTextContent(/Keyword matches the words and codes/);
  expect(intro).toHaveTextContent(/Hybrid merges the vector and keyword rankings/);
  expect(intro.textContent).not.toMatch(/\b(better|best|worse|recommended|most accurate)\b/i);
});

test("labels per mode: similarity in vector and hybrid only, a rank and a note in keyword, an order note in hybrid", async () => {
  routeFetch({
    "POST /api/search": byMode({
      vector: () => Response.json([hit("a", { score: 0.9, vector_rank: 1 })]),
      keyword: () => Response.json([hit("b", { score: null, vector_rank: null, keyword_rank: 1, found_by: ["keyword"] })]),
      hybrid: () => Response.json([both("a", 2, 1, 0.31)]),
    }),
  });
  render(<CompareView />);
  await search();
  const vector = await screen.findByRole("region", { name: "Vector" });
  const keyword = await screen.findByRole("region", { name: "Keyword" });
  const hybrid = await screen.findByRole("region", { name: "Hybrid" });
  await within(hybrid).findByRole("list");

  expect(vector).toHaveTextContent("Similarity 0.900");
  expect(vector).toHaveTextContent("Passages whose meaning is closest to the question.");
  expect(vector).not.toHaveTextContent("returns no keyword score");

  expect(keyword).not.toHaveTextContent("Similarity");
  expect(keyword).not.toHaveTextContent(/\bScore\b/);
  expect(keyword).toHaveTextContent("Keyword rank 1");
  expect(keyword).toHaveTextContent("The API returns no keyword score, only the rank.");

  expect(hybrid).toHaveTextContent("Similarity 0.310");
  expect(hybrid).toHaveTextContent("The order combines the two ranks, which is why the similarity values are not descending.");
  expect(within(vector).queryByText(/order combines/)).toBeNull();
  expect(within(keyword).queryByText(/order combines/)).toBeNull();
});

test("the similarity value has a tooltip and an accessible explanation", async () => {
  routeFetch({ "POST /api/search": byMode({ vector: () => Response.json([hit("a")]), keyword: () => Response.json([]), hybrid: () => Response.json([]) }) });
  render(<CompareView />);
  await search();
  const sim = await screen.findByText(/Similarity 0\.500/);
  expect(sim).toHaveAttribute("title", expect.stringContaining("Cosine similarity"));
  expect(sim).toHaveTextContent("Only comparable within one column");
});

test("why-listed line: found by both, by one branch (hybrid vs single column), and with neither rank", async () => {
  routeFetch({
    "POST /api/search": byMode({
      vector: () => Response.json([hit("a", { vector_rank: 3, keyword_rank: null })]),
      keyword: () => Response.json([hit("b", { score: null, vector_rank: null, keyword_rank: 2, found_by: ["keyword"] })]),
      hybrid: () =>
        Response.json([
          both("a", 3, 1),
          hit("v", { vector_rank: 4, keyword_rank: null }),
          hit("k", { vector_rank: null, keyword_rank: 2, found_by: ["keyword"] }),
          hit("n", { vector_rank: null, keyword_rank: null, found_by: [] }),
        ]),
    }),
  });
  render(<CompareView />);
  await search();
  const hybrid = within(await screen.findByRole("list", { name: "Hybrid results" })).getAllByRole("listitem");
  expect(hybrid.map((li) => li.querySelector("p")?.textContent)).toEqual([
    "Vector rank 3 · Keyword rank 1",
    "Found by vector only (rank 4)",
    "Found by keyword only (rank 2)",
    "No rank was reported for this passage",
  ]);
  // the line comes first in every item, ahead of the title
  expect(hybrid[0]!.textContent!.startsWith("Vector rank 3 · Keyword rank 1")).toBe(true);
  const v = within(await screen.findByRole("list", { name: "Vector results" })).getAllByRole("listitem");
  expect(v[0]!.textContent!.startsWith("Vector rank 3")).toBe(true);
  const k = within(await screen.findByRole("list", { name: "Keyword results" })).getAllByRole("listitem");
  expect(k[0]!.textContent!.startsWith("Keyword rank 2")).toBe(true);
});

const ok = (doc: string) => () => Response.json([hit(doc)]);
const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
const shown = () => ["Vector", "Keyword", "Hybrid"].filter((n) => within(screen.getByRole("region", { name: n })).queryByRole("list"));

test("staged reveal: Vector, then Keyword, then Hybrid about 700 ms apart, each with its caption", async () => {
  motion(false);
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  routeFetch({ "POST /api/search": byMode({ vector: ok("a"), keyword: ok("b"), hybrid: ok("c") }) });
  render(<CompareView />);
  await search();
  await tick(50); // all three responses have arrived by now
  expect(shown()).toEqual(["Vector"]);
  expect(screen.getByRole("region", { name: "Vector" })).toHaveTextContent("closest to the question");
  expect(screen.getByRole("region", { name: "Keyword" })).toHaveTextContent("Searching…");
  expect(screen.getByRole("region", { name: "Hybrid" })).toHaveTextContent("Searching…");
  await tick(700);
  expect(shown()).toEqual(["Vector", "Keyword"]);
  expect(screen.getByRole("region", { name: "Keyword" })).toHaveTextContent("contain the question's words or codes");
  await tick(700);
  expect(shown()).toEqual(["Vector", "Keyword", "Hybrid"]);
  expect(screen.getByRole("region", { name: "Hybrid" })).toHaveTextContent("merged into one list");
});

test("staged reveal keeps the order when a later column answers first, and a slow first column holds the rest", async () => {
  motion(false);
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  let releaseVector!: () => void;
  const gate = new Promise<void>((r) => (releaseVector = r));
  routeFetch({
    "POST /api/search": byMode({
      vector: (async () => { await gate; return Response.json([hit("a")]); }) as unknown as () => Response,
      keyword: ok("b"),
      hybrid: ok("c"),
    }),
  });
  render(<CompareView />);
  await search();
  await tick(5000);
  expect(shown()).toEqual([]); // keyword and hybrid are ready but Vector goes first
  releaseVector();
  await tick(50);
  expect(shown()).toEqual(["Vector", "Keyword", "Hybrid"]); // their turns have already passed
});

test("errors show at once, before their turn", async () => {
  motion(false);
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  routeFetch({
    "POST /api/search": byMode({ vector: ok("a"), keyword: ok("b"), hybrid: () => new Response("{}", { status: 500 }) }),
  });
  render(<CompareView />);
  await search();
  await tick(50);
  expect(screen.getByRole("alert")).toBeInTheDocument();
  expect(shown()).toEqual(["Vector"]);
});

test("under prefers-reduced-motion everything appears at once, with no timers needed", async () => {
  motion(true);
  routeFetch({ "POST /api/search": byMode({ vector: ok("a"), keyword: ok("b"), hybrid: ok("c") }) });
  render(<CompareView />);
  await search();
  await waitFor(() => expect(shown()).toEqual(["Vector", "Keyword", "Hybrid"]));
});

test("the 'Only in this list' badge waits for all three columns to load, not just to be revealed", async () => {
  motion(false);
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  let releaseHybrid!: () => void;
  const gate = new Promise<void>((r) => (releaseHybrid = r));
  routeFetch({
    "POST /api/search": byMode({
      vector: ok("a"),
      keyword: ok("b"),
      hybrid: (async () => { await gate; return Response.json([hit("b")]); }) as unknown as () => Response,
    }),
  });
  render(<CompareView />);
  await search();
  await tick(3000);
  expect(shown()).toEqual(["Vector", "Keyword"]);
  expect(markerCount()).toBe(0);
  releaseHybrid();
  await tick(50);
  expect(markerCount()).toBe(1);
});
