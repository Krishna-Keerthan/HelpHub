import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { resetSessionCache } from "@/lib/query/client";
import { COMPARE_QUERY_STORAGE } from "@/lib/session/storage";
import { REVEAL_STEP_MS } from "@/lib/ui/compare";
import { render } from "@/test/render";
import { routeFetch } from "@/test/fetch-mock";
import { CompareView } from "./CompareView";

const hit = (doc: string) => ({
  char_end: 10, char_start: 0, chunk_id: `chunk-${doc}`, chunk_index: 0, content: `Snippet of ${doc}`,
  document_id: doc, document_title: `Title ${doc}`, found_by: ["vector"], keyword_rank: null,
  rrf_score: 0.1, score: 0.5, vector_rank: 1,
});
const motion = (reduce: boolean) =>
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: reduce && q.includes("reduce"), media: q }));
const answers = () => ({
  "POST /api/search": async (req: Request) => {
    const { mode } = (await req.json()) as { mode: string };
    return Response.json([hit(mode)]);
  },
});
const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
// Column headings are "Meaning (vector)" etc.; the short names below are only the labels used in assertions.
const REGION: Record<string, string> = { Vector: "Meaning (vector)", Keyword: "Exact words (keyword)", Hybrid: "Combined (hybrid)" };
const shown = () =>
  ["Vector", "Keyword", "Hybrid"].filter((n) => within(screen.getByRole("region", { name: REGION[n] })).queryByRole("list"));

afterEach(() => vi.useRealTimers());

function submit(q: string) {
  fireEvent.change(screen.getByLabelText("Search query"), { target: { value: q } });
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
}

test("a submitted query is stored, and only the query", async () => {
  motion(true);
  routeFetch(answers());
  render(<CompareView />);
  submit("  refunds ");
  await screen.findAllByRole("list", { name: /results$/ });
  expect(sessionStorage.getItem(COMPARE_QUERY_STORAGE)).toBe("refunds");
  expect(sessionStorage.length).toBe(1);
});

test("page change: remounting shows the results from the cache with no search request", async () => {
  motion(false); // the restore must not be staged even though motion is allowed
  const f = routeFetch(answers());
  const first = render(<CompareView />);
  submit("refunds");
  await waitFor(() => expect(f.calls).toHaveLength(3));
  await screen.findByRole("list", { name: "Hybrid results" }, { timeout: 4000 });
  first.unmount();
  f.calls.length = 0;

  render(<CompareView />);
  expect(await screen.findByText("Title vector")).toBeInTheDocument();
  expect(screen.getByText("Title keyword")).toBeInTheDocument();
  expect(screen.getByText("Title hybrid")).toBeInTheDocument();
  expect(screen.getByLabelText("Search query")).toHaveValue("refunds");
  expect(f.calls).toHaveLength(0);
});

test("F5: an empty cache re-runs the three searches and columns appear as they arrive, without a step delay", async () => {
  motion(false);
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  sessionStorage.setItem(COMPARE_QUERY_STORAGE, "refunds");
  const open: Record<string, () => void> = {};
  const gates = Object.fromEntries(
    ["vector", "keyword", "hybrid"].map((m) => [m, new Promise<void>((r) => (open[m] = r))]),
  );
  const f = routeFetch({
    "POST /api/search": async (req) => {
      const { mode } = (await req.json()) as { mode: string };
      await gates[mode];
      return Response.json([hit(mode)]);
    },
  });
  render(<CompareView />);
  await tick(0);
  expect(f.calls).toHaveLength(3);
  expect(screen.getByLabelText("Search query")).toHaveValue("refunds");
  open.hybrid!();
  await tick(10);
  expect(shown()).toEqual(["Hybrid"]); // a staged reveal would hold it back until Vector and Keyword showed
  open.keyword!();
  await tick(10);
  expect(shown()).toEqual(["Keyword", "Hybrid"]);
  open.vector!();
  await tick(10);
  expect(shown()).toEqual(["Vector", "Keyword", "Hybrid"]);
});

test("a normal click after a restore is staged again", async () => {
  motion(false);
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  sessionStorage.setItem(COMPARE_QUERY_STORAGE, "refunds");
  routeFetch(answers());
  render(<CompareView />);
  await tick(10);
  expect(shown()).toEqual(["Vector", "Keyword", "Hybrid"]);
  submit("shipping");
  await tick(10);
  expect(shown()).toEqual(["Vector"]);
  await tick(REVEAL_STEP_MS);
  expect(shown()).toEqual(["Vector", "Keyword"]);
  await tick(REVEAL_STEP_MS);
  expect(shown()).toEqual(["Vector", "Keyword", "Hybrid"]);
});

test("a failed search is not cached: Try again really searches again", async () => {
  motion(true);
  let n = 0;
  const f = routeFetch({
    "POST /api/search": async (req) => {
      const { mode } = (await req.json()) as { mode: string };
      if (mode === "keyword" && n++ === 0) return Response.json({ detail: "x" }, { status: 500 });
      return Response.json([hit(mode)]);
    },
  });
  render(<CompareView />);
  submit("refunds");
  fireEvent.click(await screen.findByRole("button", { name: "Retry Keyword" }));
  expect(await screen.findByRole("list", { name: "Keyword results" })).toBeInTheDocument();
  expect(f.calls).toHaveLength(4);
});

test("restoring a query when the cache was cleared by a session end runs the searches again", async () => {
  motion(true);
  routeFetch(answers());
  const first = render(<CompareView />);
  submit("refunds");
  await screen.findByRole("list", { name: "Hybrid results" });
  first.unmount();
  resetSessionCache();
  const f = routeFetch(answers());
  render(<CompareView />);
  await screen.findByRole("list", { name: "Hybrid results" });
  expect(f.calls).toHaveLength(3);
});

test("blocked storage does not break compare", async () => {
  motion(true);
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  routeFetch(answers());
  render(<CompareView />);
  submit("refunds");
  expect(await screen.findByRole("list", { name: "Vector results" })).toBeInTheDocument();
  vi.restoreAllMocks();
});
