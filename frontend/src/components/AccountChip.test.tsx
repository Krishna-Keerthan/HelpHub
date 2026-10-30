import { screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";
import { getQueryClient } from "@/lib/query/client";
import { queryKeys } from "@/lib/query/hooks";
import { routeFetch } from "@/test/fetch-mock";
import { render } from "@/test/render";
import { AccountChip } from "./AccountChip";

const me = { id: "u1", tenant_id: "t1", email: "ada@example.test", role: "agent", is_active: true, created_at: "2026-01-01T00:00:00Z" };

test("shows the email (full address in title) and the role for a successful response", async () => {
  routeFetch({ "GET /api/auth/me": () => Response.json(me) });
  render(<AccountChip />);
  expect(screen.getByTestId("account-chip-placeholder")).toBeInTheDocument();
  const email = await screen.findByText("ada@example.test");
  expect(email).toHaveAttribute("title", "ada@example.test");
  expect(screen.getByText("agent")).toBeInTheDocument();
  expect(screen.queryByTestId("account-chip-placeholder")).toBeNull();
});

test.each([
  ["a 500", () => new Response("boom", { status: 500 })],
  ["a 401", () => Response.json({ code: "unauthorized" }, { status: 401 })],
  ["a body without a role", () => Response.json({ email: "ada@example.test" })],
])("shows nothing after %s (no banner, no placeholder)", async (_n, handler) => {
  const f = routeFetch({ "GET /api/auth/me": handler });
  const { container } = render(<AccountChip />);
  await waitFor(() => expect(f.calls.length).toBeGreaterThan(0));
  await waitFor(() => expect(screen.queryByTestId("account-chip-placeholder")).toBeNull());
  expect(container).toBeEmptyDOMElement();
});

test("no extra request when /auth/me is already cached", () => {
  const f = routeFetch({});
  getQueryClient().setQueryData(queryKeys.me, { role: "admin", email: "root@example.test" });
  render(<AccountChip />);
  expect(screen.getByText("root@example.test")).toBeInTheDocument();
  expect(screen.getByText("admin")).toBeInTheDocument();
  expect(f.calls).toHaveLength(0);
});
