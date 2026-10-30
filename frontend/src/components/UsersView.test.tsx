import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { resetSessionCache } from "@/lib/query/client";
import { render } from "@/test/render";
import { routeFetch } from "@/test/fetch-mock";
import { UsersView } from "./UsersView";
import { UsersNavLink } from "./UsersNavLink";

afterEach(() => vi.restoreAllMocks());

vi.mock("next/navigation", () => ({ usePathname: () => "/users" }));

const user = (email: string, role = "agent", active = true) => ({
  id: email, email, role, is_active: active, tenant_id: "t", created_at: "2026-01-01T00:00:00Z",
});
const me = (role: string) => ({ "GET /api/auth/me": () => Response.json({ id: "u", email: "u@x.co", role }) });
const list = (rows = [user("a@x.co", "admin")]) => ({ "GET /api/users": () => Response.json(rows) });
const NOT_ADMIN = "Only workspace admins can manage users.";

// Fail closed: every non-confirmed-admin shape shows the message, no form, and never asks for the users.
test.each([
  ["viewer", me("viewer")],
  ["agent", me("agent")],
  ["unknown role", me("owner")],
  ["403", { "GET /api/auth/me": () => new Response("{}", { status: 403 }) }],
  ["500", { "GET /api/auth/me": () => new Response("", { status: 500 }) }],
  ["not JSON", { "GET /api/auth/me": () => new Response("<html>", { status: 200 }) }],
  ["missing role", { "GET /api/auth/me": () => Response.json({ id: "u" }) }],
])("%s: read-only message, no form, no users request", async (_name, routes) => {
  const f = routeFetch({ ...routes, ...list() });
  render(<UsersView />);
  expect(await screen.findByText(NOT_ADMIN)).toBeInTheDocument();
  expect(screen.queryByRole("form", { name: "Add a user" })).toBeNull();
  expect(f.keys()).not.toContain("GET /api/users");
});

test("pending lookup shows no form", () => {
  routeFetch({ "GET /api/auth/me": () => new Promise<Response>(() => {}), ...list() });
  render(<UsersView />);
  expect(screen.getByText("Checking your access…")).toBeInTheDocument();
  expect(screen.queryByRole("form", { name: "Add a user" })).toBeNull();
  expect(screen.queryByText(NOT_ADMIN)).toBeNull();
});

test("admin sees a table with Email, Role, Status and Created columns and one row per user", async () => {
  routeFetch({ ...me("admin"), ...list([user("a@x.co", "admin"), user("v@x.co", "viewer", false)]) });
  render(<UsersView />);
  const table = await screen.findByRole("table", { name: "Users in this workspace" });
  expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Email", "Role", "Status", "Created"]);
  const rows = within(table).getAllByRole("row").slice(1);
  expect(rows).toHaveLength(2);
  const cells = (r: HTMLElement) => within(r).getAllByRole("cell").map((c) => c.textContent);
  expect(cells(rows[0]!)).toEqual(["a@x.co", "admin", "Active", new Date("2026-01-01T00:00:00Z").toLocaleDateString()]);
  expect(cells(rows[1]!).slice(0, 3)).toEqual(["v@x.co", "viewer", "Inactive"]);
});

test("the created cell shows the local date and keeps the full timestamp in its title; the email keeps its full address", async () => {
  routeFetch({ ...me("admin"), ...list([user("long.address@example.test")]) });
  render(<UsersView />);
  const row = (await screen.findAllByRole("row"))[1]!;
  const [email, , , created] = within(row).getAllByRole("cell");
  expect(email).toHaveAttribute("title", "long.address@example.test");
  expect(created).toHaveAttribute("title", new Date("2026-01-01T00:00:00Z").toLocaleString());
});

test("a created_at that is not a date is shown as received, not as 'Invalid Date'", async () => {
  routeFetch({ ...me("admin"), "GET /api/users": () => Response.json([{ ...user("a@x.co"), created_at: "soon" }]) });
  render(<UsersView />);
  const row = (await screen.findAllByRole("row"))[1]!;
  expect(row).toHaveTextContent("soon");
  expect(row).not.toHaveTextContent("Invalid Date");
});

test("the table scrolls inside its own container, so the page does not overflow", async () => {
  routeFetch({ ...me("admin"), ...list() });
  render(<UsersView />);
  const table = await screen.findByRole("table");
  expect(table.parentElement!.className).toContain("overflow-x-auto");
});

test("count line: 1 user, N users, and the first-100 note only at exactly 100 rows", async () => {
  routeFetch({ ...me("admin"), ...list([user("a@x.co")]) });
  const one = render(<UsersView />);
  expect(await screen.findByText("1 user")).toBeInTheDocument();
  one.unmount();
  resetSessionCache();

  routeFetch({ ...me("admin"), ...list([user("a@x.co"), user("b@x.co")]) });
  const two = render(<UsersView />);
  expect(await screen.findByText("2 users")).toBeInTheDocument();
  expect(screen.queryByText(/first 100/)).toBeNull();
  two.unmount();
  resetSessionCache();

  for (const n of [99, 100]) {
    routeFetch({ ...me("admin"), ...list(Array.from({ length: n }, (_, i) => user(`u${i}@x.co`))) });
    const r = render(<UsersView />);
    expect(await screen.findByText(new RegExp(`^${n} users`))).toBeInTheDocument();
    if (n === 100) expect(screen.getByText(/Showing the first 100 users\./)).toBeInTheDocument();
    else expect(screen.queryByText(/first 100/)).toBeNull();
    r.unmount();
    resetSessionCache();
  }
});

test("the header note says there is no password reset or deactivate action", async () => {
  routeFetch({ ...me("admin"), ...list() });
  render(<UsersView />);
  expect(await screen.findByText(/People who can sign in to this workspace\./)).toHaveTextContent(
    "There is no password reset or deactivate action yet. Ask the workspace operator.",
  );
});

test("a non-admin sees only the read-only message: no table, no note", async () => {
  routeFetch({ ...me("agent"), ...list() });
  render(<UsersView />);
  expect(await screen.findByText(NOT_ADMIN)).toBeInTheDocument();
  expect(screen.queryByRole("table")).toBeNull();
  expect(screen.queryByText(/password reset/)).toBeNull();
});

async function fillAndSubmit(password = "twelve-plus-chars") {
  await screen.findByRole("form", { name: "Add a user" });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@x.co" } });
  fireEvent.change(screen.getByLabelText("Role"), { target: { value: "viewer" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.submit(screen.getByRole("form", { name: "Add a user" }));
}

test("add success posts the body, refetches the list and clears the form", async () => {
  let rows = [user("a@x.co", "admin")];
  const f = routeFetch({
    ...me("admin"),
    "GET /api/users": () => Response.json(rows),
    "POST /api/users": () => {
      rows = [...rows, user("new@x.co", "viewer")];
      return Response.json(user("new@x.co", "viewer"), { status: 201 });
    },
  });
  render(<UsersView />);
  await fillAndSubmit();
  expect(await screen.findByText("new@x.co", { selector: "td" })).toBeInTheDocument();
  expect(await f.calls.find((c) => c.key === "POST /api/users")!.req.json()).toEqual({
    email: "new@x.co", role: "viewer", password: "twelve-plus-chars",
  });
  expect(f.keys().filter((k) => k === "GET /api/users")).toHaveLength(2);
  expect(screen.getByLabelText("Password")).toHaveValue("");
  expect(screen.getByRole("status")).toHaveTextContent("Added new@x.co");
  expect(document.body.textContent).not.toContain("twelve-plus-chars");
});

test.each([
  [409, "already exists"],
  [403, NOT_ADMIN],
  [422, "12 to 128 characters"],
  [429, "Try again in 7 seconds"],
])("add error %i shows a clear message", async (status, text) => {
  routeFetch({
    ...me("admin"), ...list(),
    "POST /api/users": () => new Response(JSON.stringify({ detail: "backend text" }), { status, headers: { "Retry-After": "7" } }),
  });
  render(<UsersView />);
  await fillAndSubmit();
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(text);
  expect(alert).not.toHaveTextContent("backend text");
});

test("a short password is blocked client-side, nothing is sent", async () => {
  const f = routeFetch({ ...me("admin"), ...list() });
  render(<UsersView />);
  await fillAndSubmit("short");
  expect(await screen.findByRole("alert")).toHaveTextContent("12 to 128");
  expect(f.keys()).not.toContain("POST /api/users");
});

test("generate shows a 16-character password once, copy works, and clearing removes it", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  routeFetch({ ...me("admin"), ...list() });
  render(<UsersView />);
  await screen.findByRole("form", { name: "Add a user" });
  fireEvent.click(screen.getByRole("button", { name: "Generate password" }));
  const shown = screen.getByRole("group", { name: "Generated password" }).querySelector("code")!.textContent!;
  expect(shown).toHaveLength(16);
  expect(screen.getByLabelText("Password")).toHaveValue(shown);
  fireEvent.click(screen.getByRole("button", { name: "Copy" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith(shown));
  fireEvent.click(screen.getByRole("button", { name: "Hide" }));
  expect(screen.queryByRole("group", { name: "Generated password" })).toBeNull();
  expect(document.body.textContent).not.toContain(shown); // type=password input value is not text content
});

test("the generated password is gone after a successful add", async () => {
  routeFetch({ ...me("admin"), ...list(), "POST /api/users": () => Response.json(user("new@x.co"), { status: 201 }) });
  render(<UsersView />);
  await screen.findByRole("form", { name: "Add a user" });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@x.co" } });
  fireEvent.click(screen.getByRole("button", { name: "Generate password" }));
  const shown = screen.getByRole("group", { name: "Generated password" }).querySelector("code")!.textContent!;
  fireEvent.submit(screen.getByRole("form", { name: "Add a user" }));
  await screen.findByText(/^Added new@x\.co/);
  expect(screen.queryByRole("group", { name: "Generated password" })).toBeNull();
  expect(document.body.textContent).not.toContain(shown);
  expect(screen.getByLabelText("Password")).toHaveValue("");
});

test("the Users nav link is shown for admin only", async () => {
  routeFetch(me("admin"));
  render(<UsersNavLink />);
  expect(await screen.findByRole("link", { name: "Users" })).toHaveAttribute("href", "/users");
});

test.each([["viewer", me("viewer")], ["failed", { "GET /api/auth/me": () => new Response("", { status: 500 }) }]])(
  "the Users nav link is hidden for %s",
  async (_n, routes) => {
    const f = routeFetch(routes);
    render(<UsersNavLink />);
    await waitFor(() => expect(f.keys()).toContain("GET /api/auth/me"));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("link", { name: "Users" })).toBeNull();
  },
);
