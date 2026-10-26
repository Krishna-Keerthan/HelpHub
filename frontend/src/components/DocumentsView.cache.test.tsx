import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { login, logout } from "@/lib/api/client";
import { DOCUMENTS_STALE_MS, getQueryClient, ME_STALE_MS } from "@/lib/query/client";
import { queryKeys } from "@/lib/query/hooks";
import { routeFetch } from "@/test/fetch-mock";
import { render } from "@/test/render";
import { DocumentsView } from "./DocumentsView";

const doc = (id: string, title: string) => ({
  id, title, status: "READY", error: null, created_by: null,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
});
const me = (role: string) => Response.json({ id: "u", email: "u@x.co", role });
const count = (f: { keys: () => string[] }, key: string) => f.keys().filter((k) => k === key).length;
const READ_ONLY = "Read-only account: uploads are disabled.";

afterEach(() => vi.useRealTimers());

test("a second visit within the fresh window shows the list at once and makes no new request", async () => {
  const f = routeFetch({
    "GET /api/documents": () => Response.json([doc("1", "Refund policy")]),
    "GET /api/auth/me": () => me("admin"),
  });
  const first = render(<DocumentsView />);
  await screen.findByText("Refund policy");
  await screen.findByLabelText("Upload a document");
  first.unmount();

  render(<DocumentsView />);
  expect(screen.getByText("Refund policy")).toBeInTheDocument(); // synchronously, from the cache
  expect(screen.getByLabelText("Upload a document")).toBeInTheDocument();
  await act(async () => {});
  expect(count(f, "GET /api/documents")).toBe(1);
  expect(count(f, "GET /api/auth/me")).toBe(1);
});

test("a stale list is shown at once and revalidated quietly; /auth/me is re-checked only after its own window", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  let title = "Old title";
  const f = routeFetch({
    "GET /api/documents": () => Response.json([doc("1", title)]),
    "GET /api/auth/me": () => me("admin"),
  });
  const first = render(<DocumentsView />);
  await screen.findByText("Old title");
  first.unmount();

  title = "New title";
  vi.setSystemTime(Date.now() + DOCUMENTS_STALE_MS + 1);
  render(<DocumentsView />);
  expect(screen.getByText("Old title")).toBeInTheDocument(); // stale data first, no spinner
  expect(await screen.findByText("New title")).toBeInTheDocument(); // then the quiet revalidation
  expect(count(f, "GET /api/documents")).toBe(2);
  expect(count(f, "GET /api/auth/me")).toBe(1); // the role is still inside its window
  expect(screen.queryByRole("alert")).toBeNull();

  cleanupAndAdvance(ME_STALE_MS);
  render(<DocumentsView />);
  await waitFor(() => expect(count(f, "GET /api/auth/me")).toBe(2));
});

function cleanupAndAdvance(ms: number) {
  document.body.innerHTML = "";
  vi.setSystemTime(Date.now() + ms + 1);
}

test("a failed revalidation keeps the last list, says so, and Try again recovers", async () => {
  let fail = false;
  const f = routeFetch({
    "GET /api/documents": () => (fail ? Response.json({}, { status: 500 }) : Response.json([doc("1", "Kept")])),
    "GET /api/auth/me": () => me("admin"),
  });
  render(<DocumentsView />);
  await screen.findByText("Kept");
  fail = true;
  await act(async () => {
    await getQueryClient().invalidateQueries({ queryKey: queryKeys.documents });
  });
  expect(await screen.findByRole("alert")).toHaveTextContent("Showing the last list that loaded");
  expect(screen.getByText("Kept")).toBeInTheDocument();
  fail = false;
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(count(f, "GET /api/documents")).toBe(3);
});

test("a failed or garbled role revalidation never turns a read-only view into a write view", async () => {
  let answer: () => Response = () => me("viewer");
  routeFetch({
    "GET /api/documents": () => Response.json([doc("1", "A")]),
    "GET /api/auth/me": () => answer(),
  });
  render(<DocumentsView />);
  await screen.findByText(READ_ONLY);

  const revalidate = () =>
    act(async () => {
      await getQueryClient().invalidateQueries({ queryKey: queryKeys.me });
    });
  for (const bad of [
    () => Response.json({}, { status: 500 }),
    () => Response.json({ role: { admin: true } }),
    () => new Response("<html>", { headers: { "Content-Type": "application/json" } }),
    () => {
      throw new TypeError("offline");
    },
  ]) {
    answer = bad;
    await revalidate();
    expect(screen.queryByLabelText("Upload a document")).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete A" })).toBeNull();
  }
});

test("an admin whose role can no longer be confirmed loses the write controls (fail closed)", async () => {
  let ok = true;
  routeFetch({
    "GET /api/documents": () => Response.json([doc("1", "A")]),
    "GET /api/auth/me": () => (ok ? me("admin") : Response.json({}, { status: 500 })),
  });
  render(<DocumentsView />);
  await screen.findByLabelText("Upload a document");
  ok = false;
  await act(async () => {
    await getQueryClient().invalidateQueries({ queryKey: queryKeys.me });
  });
  await screen.findByText(READ_ONLY);
  expect(screen.queryByRole("button", { name: "Delete A" })).toBeNull();
});

test("login clears the cache: a viewer's cached role and list never appear in a later admin session", async () => {
  let role = "viewer";
  let title = "Viewer's list";
  const f = routeFetch({
    "GET /api/documents": () => Response.json([doc("1", title)]),
    "GET /api/auth/me": () => me(role),
    "POST /api/auth/login": () => Response.json({}),
  });
  const first = render(<DocumentsView />);
  await screen.findByText(READ_ONLY);
  first.unmount();
  expect(getQueryClient().getQueryData(queryKeys.me)).toBeDefined();

  role = "admin";
  title = "Admin's list";
  await login({ email: "a@x.co", password: "pw", tenant_slug: "t" });
  expect(getQueryClient().getQueryData(queryKeys.me)).toBeUndefined();
  expect(getQueryClient().getQueryData(queryKeys.documents)).toBeUndefined();

  render(<DocumentsView />);
  expect(screen.queryByText("Viewer's list")).toBeNull();
  expect(screen.queryByText(READ_ONLY)).toBeNull();
  expect(await screen.findByLabelText("Upload a document")).toBeInTheDocument();
  expect(await screen.findByText("Admin's list")).toBeInTheDocument();
  expect(count(f, "GET /api/auth/me")).toBe(2);
});

test("logout clears the cache, even when the logout request fails", async () => {
  routeFetch({
    "GET /api/documents": () => Response.json([doc("1", "A")]),
    "GET /api/auth/me": () => me("admin"),
    "POST /api/auth/logout": () => {
      throw new TypeError("offline");
    },
  });
  const first = render(<DocumentsView />);
  await screen.findByLabelText("Upload a document");
  first.unmount();
  await expect(logout()).rejects.toThrow();
  expect(getQueryClient().getQueryData(queryKeys.me)).toBeUndefined();
  expect(getQueryClient().getQueryData(queryKeys.documents)).toBeUndefined();
});

test("a login that races an in-flight old-session request is not repopulated by it", async () => {
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  routeFetch({
    "GET /api/documents": () => Response.json([]),
    "GET /api/auth/me": async () => {
      await gate;
      return me("viewer"); // answered for the OLD session, after the login
    },
    "POST /api/auth/login": () => Response.json({}),
  });
  const page = render(<DocumentsView />);
  await act(async () => {});
  page.unmount(); // the user leaves for the login page while /auth/me is still in flight
  await login({ email: "a@x.co", password: "pw", tenant_slug: "t" });
  release();
  await act(async () => {});
  expect(getQueryClient().getQueryData(queryKeys.me)).toBeUndefined();
});

test("nothing is written to localStorage or sessionStorage", async () => {
  routeFetch({
    "GET /api/documents": () => Response.json([doc("1", "Secret title")]),
    "GET /api/auth/me": () => me("admin"),
  });
  const writes = vi.spyOn(Storage.prototype, "setItem");
  render(<DocumentsView />);
  await screen.findByText("Secret title");
  await screen.findByLabelText("Upload a document");
  expect(writes).not.toHaveBeenCalled();
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
  writes.mockRestore();
});
