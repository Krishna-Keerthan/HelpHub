import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { resetSessionCache } from "@/lib/query/client";
import { render } from "@/test/render";
import { routeFetch } from "@/test/fetch-mock";
import { DocumentsView } from "./DocumentsView";

const nav = vi.hoisted(() => ({ search: "", push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  usePathname: () => "/documents",
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const doc = (id: string, title: string, status = "READY") => ({
  id,
  title,
  status,
  error: null,
  created_by: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

afterEach(() => vi.restoreAllMocks());

// The role lookup (GET /api/auth/me) is not what these tests are about.
const docKeys = (f: { keys: () => string[] }) => f.keys().filter((k) => k !== "GET /api/auth/me");

const me = (role: string) => ({ "GET /api/auth/me": () => Response.json({ id: "u", email: "u@x.co", role }) });
const asAdmin = me("admin");

const pick = async (file: File) =>
  fireEvent.change(await screen.findByLabelText("Upload a document"), { target: { files: [file] } });

test("a file over 4 MB is rejected client-side with a clear message and nothing is sent", async () => {
  const f = routeFetch({
    ...asAdmin, "GET /api/documents": () => Response.json([]) });
  render(<DocumentsView />);
  await screen.findByText("No documents yet.");
  await pick(new File([new Uint8Array(4 * 1024 * 1024 + 1)], "big.pdf", { type: "application/pdf" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("limited to 4 MB");
  expect(docKeys(f)).toEqual(["GET /api/documents"]);
});

test("delete asks for confirmation; cancel sends nothing, confirm deletes", async () => {
  let remaining = [doc("1", "Refund policy")];
  const f = routeFetch({
    ...asAdmin,
    "GET /api/documents": () => Response.json(remaining),
    "DELETE /api/documents/1": () => {
      remaining = [];
      return new Response(null, { status: 204 });
    },
  });
  render(<DocumentsView />);
  const del = await screen.findByRole("button", { name: "Delete Refund policy" });

  vi.spyOn(window, "confirm").mockReturnValueOnce(false);
  fireEvent.click(del);
  expect(docKeys(f)).toEqual(["GET /api/documents"]);

  vi.spyOn(window, "confirm").mockReturnValueOnce(true);
  fireEvent.click(del);
  await waitFor(() => expect(screen.queryByText("Refund policy")).not.toBeInTheDocument());
  expect(f.keys()).toContain("DELETE /api/documents/1");
  // the list is invalidated after a delete, so it is refetched from the server
  await waitFor(() => expect(f.keys().filter((k) => k === "GET /api/documents")).toHaveLength(2));
});

test("a viewer sees no upload control and a read-only note", async () => {
  routeFetch({
    "GET /api/documents": () => Response.json([doc("1", "A")]),
    "GET /api/auth/me": () => Response.json({ id: "u", email: "v@x.co", role: "viewer" }),
  });
  render(<DocumentsView />);
  await screen.findByText("Read-only account: uploads are disabled.");
  expect(screen.queryByLabelText("Upload a document")).toBeNull();
});

test("a 403 on upload says the account is read-only", async () => {
  routeFetch({
    ...asAdmin,
    "GET /api/documents": () => Response.json([]),
    "POST /api/documents/upload": () => Response.json({ detail: "Forbidden" }, { status: 403 }),
  });
  render(<DocumentsView />);
  await screen.findByText("No documents yet.");
  await pick(new File(["x"], "a.txt"));
  expect(await screen.findByRole("alert")).toHaveTextContent("read-only");
});

const noWriteControls = () => {
  expect(screen.queryByLabelText("Upload a document")).toBeNull();
  expect(screen.queryByRole("button", { name: /^Delete / })).toBeNull();
};

test("a viewer sees neither Upload nor Delete", async () => {
  routeFetch({ ...me("viewer"), "GET /api/documents": () => Response.json([doc("1", "Refund policy")]) });
  render(<DocumentsView />);
  await screen.findByText("Read-only account: uploads are disabled.");
  expect(screen.getByText("Refund policy")).toBeInTheDocument();
  noWriteControls();
});

test("write controls stay hidden while the role is still being looked up", async () => {
  routeFetch({
    "GET /api/auth/me": () => new Promise<Response>(() => {}),
    "GET /api/documents": () => Response.json([doc("1", "Refund policy")]),
  });
  render(<DocumentsView />);
  await screen.findByText("Refund policy");
  noWriteControls();
});

test("if /auth/me fails, returns an error status or cannot be parsed, the view is read-only", async () => {
  const bad: Record<string, () => Response> = {
    "network error": () => {
      throw new TypeError("offline");
    },
    "500": () => Response.json({ detail: "boom" }, { status: 500 }),
    "401": () => Response.json({ detail: "no" }, { status: 401 }),
    "not json": () => new Response("<html>", { status: 200, headers: { "Content-Type": "application/json" } }),
    "missing role": () => Response.json({ id: "u" }),
    "unknown role": () => Response.json({ id: "u", role: "owner-ish" }),
    "role not a string": () => Response.json({ id: "u", role: { x: 1 } }),
  };
  for (const [label, handler] of Object.entries(bad)) {
    routeFetch({ "GET /api/auth/me": handler, "GET /api/documents": () => Response.json([doc("1", label)]) });
    const { unmount } = render(<DocumentsView />);
    await screen.findByText(label, { selector: "span" });
    await screen.findByText("Read-only account: uploads are disabled.");
    noWriteControls();
    unmount();
    resetSessionCache();
  }
});

test("an agent sees Upload but not Delete; an admin sees both", async () => {
  for (const [role, canDelete] of [["agent", false], ["admin", true]] as const) {
    routeFetch({ ...me(role), "GET /api/documents": () => Response.json([doc("1", "A")]) });
    const { unmount } = render(<DocumentsView />);
    expect(await screen.findByLabelText("Upload a document")).toBeInTheDocument();
    await screen.findByText("A");
    expect(screen.queryByRole("button", { name: "Delete A" }) !== null, role).toBe(canDelete);
    unmount();
    resetSessionCache();
  }
});
