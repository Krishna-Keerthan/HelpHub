import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { getQueryClient } from "@/lib/query/client";
import { afterDocumentsChanged } from "@/lib/query/invalidate";
import { queryKeys } from "@/lib/query/hooks";
import { routeFetch } from "@/test/fetch-mock";
import { render } from "@/test/render";
import { DocumentsView } from "./DocumentsView";

const nav = vi.hoisted(() => ({ search: "", push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  usePathname: () => "/documents",
  useSearchParams: () => new URLSearchParams(nav.search),
}));

beforeEach(() => {
  nav.search = "";
  nav.push.mockClear();
  nav.replace.mockClear();
});

const doc = (n: number) => ({
  id: String(n), title: `Doc ${n}`, status: "READY", error: null, created_by: null,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
});
const all = (n: number) => Array.from({ length: n }, (_, i) => doc(i + 1));
const asViewer = { "GET /api/auth/me": () => Response.json({ id: "u", email: "u@x.co", role: "viewer" }) };
const asAdmin = { "GET /api/auth/me": () => Response.json({ id: "u", email: "u@x.co", role: "admin" }) };

/** A backend with `rows` documents honouring limit/offset; `header` says what X-Total-Count to send (null: none). */
function backend(rows: ReturnType<typeof all>, header: (n: number) => string | null = (n) => String(n)) {
  const seen: { limit: string | null; offset: string | null }[] = [];
  const handler = (req: Request) => {
    const q = new URL(req.url).searchParams;
    seen.push({ limit: q.get("limit"), offset: q.get("offset") });
    const limit = Number(q.get("limit"));
    const offset = Number(q.get("offset"));
    const headers: Record<string, string> = {};
    const h = header(rows.length);
    if (h !== null) headers["x-total-count"] = h;
    return Response.json(rows.slice(offset, offset + limit), { headers });
  };
  return { handler, seen };
}

test("24 documents, page size 10: first request is limit=10 offset=0 and the footer says 'of 24'", async () => {
  const b = backend(all(24));
  routeFetch({ ...asViewer, "GET /api/documents": b.handler });
  render(<DocumentsView />);
  expect(await screen.findByText("Showing 1 to 10 of 24")).toBeInTheDocument();
  expect(b.seen[0]).toEqual({ limit: "10", offset: "0" });
  expect(screen.getAllByRole("listitem")).toHaveLength(10);
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(nav.push).toHaveBeenCalledWith("/documents?page=2", { scroll: false });
});

test("the last page (page=3) requests offset=20, shows 4 rows, and Next is disabled", async () => {
  nav.search = "page=3";
  const b = backend(all(24));
  routeFetch({ ...asViewer, "GET /api/documents": b.handler });
  render(<DocumentsView />);
  expect(await screen.findByText("Showing 21 to 24 of 24")).toBeInTheDocument();
  expect(b.seen[0]).toEqual({ limit: "10", offset: "20" });
  expect(screen.getAllByRole("listitem")).toHaveLength(4);
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
});

test("size in the URL is used, and changing the size resets to page 1 in the URL", async () => {
  nav.search = "page=2&size=25";
  const b = backend(all(60));
  routeFetch({ ...asViewer, "GET /api/documents": b.handler });
  render(<DocumentsView />);
  expect(await screen.findByText("Showing 26 to 50 of 60")).toBeInTheDocument();
  expect(b.seen[0]).toEqual({ limit: "25", offset: "25" });
  fireEvent.change(screen.getByLabelText("Per page"), { target: { value: "50" } });
  expect(nav.push).toHaveBeenCalledWith("/documents?size=50", { scroll: false });
});

test("invalid URL values fall back to page 1 and size 10", async () => {
  nav.search = "page=abc&size=7";
  const b = backend(all(24));
  routeFetch({ ...asViewer, "GET /api/documents": b.handler });
  render(<DocumentsView />);
  await screen.findByText("Showing 1 to 10 of 24");
  expect(b.seen[0]).toEqual({ limit: "10", offset: "0" });
});

test("without X-Total-Count the footer says 'Page 1' and Next follows whether the page is full", async () => {
  const b = backend(all(24), () => null);
  routeFetch({ ...asViewer, "GET /api/documents": b.handler });
  render(<DocumentsView />);
  expect(await screen.findByText("Page 1")).toBeInTheDocument();
  expect(screen.queryByText(/ of \d+/)).toBeNull();
  expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
});

test("without X-Total-Count, a short page disables Next", async () => {
  nav.search = "page=3";
  const b = backend(all(24), () => null);
  routeFetch({ ...asViewer, "GET /api/documents": b.handler });
  render(<DocumentsView />);
  expect(await screen.findByText("Page 3")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
});

test.each(["abc", "", "-3", "1.5", "99999999999999"])("an unparsable X-Total-Count (%j) is treated as absent", async (value) => {
  const b = backend(all(24), () => value);
  routeFetch({ ...asViewer, "GET /api/documents": b.handler });
  render(<DocumentsView />);
  expect(await screen.findByText("Page 1")).toBeInTheDocument();
});

test("a page past the end moves to the last page when the total is known", async () => {
  nav.search = "page=9";
  const b = backend(all(24));
  routeFetch({ ...asViewer, "GET /api/documents": b.handler });
  render(<DocumentsView />);
  await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/documents?page=3", { scroll: false }));
});

test("a page past the end moves back one page when no total is known", async () => {
  nav.search = "page=3";
  const b = backend(all(15), () => null);
  routeFetch({ ...asViewer, "GET /api/documents": b.handler });
  render(<DocumentsView />);
  await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/documents?page=2", { scroll: false }));
});

test("page 1 with no documents shows the empty state, not a redirect", async () => {
  routeFetch({ ...asViewer, "GET /api/documents": backend([]).handler });
  render(<DocumentsView />);
  expect(await screen.findByText("No documents yet.")).toBeInTheDocument();
  expect(nav.replace).not.toHaveBeenCalled();
  expect(screen.queryByRole("navigation", { name: "Pagination" })).toBeNull();
});

test("deleting the only row on the last page moves to the previous page", async () => {
  nav.search = "page=3";
  let rows = all(21);
  const f = routeFetch({
    ...asAdmin,
    "GET /api/documents": (req) => backend(rows).handler(req),
    "DELETE /api/documents/21": () => {
      rows = rows.filter((d) => d.id !== "21");
      return new Response(null, { status: 204 });
    },
  });
  render(<DocumentsView />);
  expect(await screen.findByText("Showing 21 to 21 of 21")).toBeInTheDocument();
  vi.spyOn(window, "confirm").mockReturnValueOnce(true);
  fireEvent.click(await screen.findByRole("button", { name: "Delete Doc 21" }));
  await waitFor(() => expect(f.keys()).toContain("DELETE /api/documents/21"));
  await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/documents?page=2", { scroll: false }));
  expect(nav.replace).toHaveBeenCalledTimes(1);
});

test("deleting a row on a middle page keeps the page and refreshes the total", async () => {
  nav.search = "page=2";
  let rows = all(24);
  routeFetch({
    ...asAdmin,
    "GET /api/documents": (req) => backend(rows).handler(req),
    "DELETE /api/documents/12": () => {
      rows = rows.filter((d) => d.id !== "12");
      return new Response(null, { status: 204 });
    },
  });
  render(<DocumentsView />);
  await screen.findByText("Showing 11 to 20 of 24");
  vi.spyOn(window, "confirm").mockReturnValueOnce(true);
  fireEvent.click(await screen.findByRole("button", { name: "Delete Doc 12" }));
  expect(await screen.findByText("Showing 11 to 20 of 23")).toBeInTheDocument();
  expect(screen.queryByText("Doc 12")).toBeNull();
  expect(nav.replace).not.toHaveBeenCalled();
});

test("invalidating the documents prefix marks every cached page and single document stale", async () => {
  const client = getQueryClient();
  const keys = [queryKeys.documentsPage(1, 10), queryKeys.documentsPage(2, 10), queryKeys.documentsPage(1, 25), queryKeys.document("d1")];
  for (const k of keys) client.setQueryData(k, { items: [], total: 0 });
  await afterDocumentsChanged(client);
  for (const k of keys) expect(client.getQueryState(k)?.isInvalidated, JSON.stringify(k)).toBe(true);
});

test("a PENDING row on the visible page keeps polling until it is no longer pending", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
  try {
    let status = "PENDING";
    const f = routeFetch({
      ...asViewer,
      "GET /api/documents": () => Response.json([{ ...doc(1), status }], { headers: { "x-total-count": "1" } }),
    });
    render(<DocumentsView />);
    await vi.waitFor(() => expect(f.keys().filter((k) => k === "GET /api/documents")).toHaveLength(1));
    status = "READY";
    await vi.advanceTimersByTimeAsync(4100);
    expect(f.keys().filter((k) => k === "GET /api/documents")).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(12000);
    expect(f.keys().filter((k) => k === "GET /api/documents")).toHaveLength(2);
  } finally {
    vi.useRealTimers();
  }
});
