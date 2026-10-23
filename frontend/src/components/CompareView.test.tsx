import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { routeFetch } from "@/test/fetch-mock";
import { DEMO_QUERIES } from "@/lib/demo-queries";
import { CompareView } from "./CompareView";

const hit = (doc: string, over: Record<string, unknown> = {}) => ({
  char_end: 10, char_start: 0, chunk_id: `chunk-${doc}-${Math.random()}`, chunk_index: 0,
  content: `Snippet of ${doc}`, document_id: doc, document_title: `Title ${doc}`,
  found_by: ["vector"], keyword_rank: null, rrf_score: 0.1, score: 0.5, vector_rank: 1, ...over,
});

afterEach(() => vi.restoreAllMocks());

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

test("shows position, title, snippet; score only when non-null; marks unique documents", async () => {
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
  expect(first).toHaveTextContent("Score 0.812");
  expect(first).toHaveTextContent("Only in this list");
  expect(second).not.toHaveTextContent("Only in this list");
  expect(keyword).not.toHaveTextContent("Score");
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
