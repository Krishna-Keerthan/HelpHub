import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { routeFetch } from "@/test/fetch-mock";
import { LoginForm } from "./LoginForm";

const replace = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(search),
}));

beforeEach(() => {
  replace.mockClear();
  search = "";
});

function fill() {
  fireEvent.change(screen.getByLabelText("Workspace"), { target: { value: "acme" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.co" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
  fireEvent.submit(screen.getByRole("form", { name: "Log in" }));
}

test("success goes to the validated next path", async () => {
  search = "next=%2Fchat";
  const f = routeFetch({ "POST /api/auth/login": () => Response.json({ ok: true }) });
  render(<LoginForm />);
  fill();
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat"));
  const body = await f.calls[0]!.req.json();
  expect(body).toEqual({ email: "a@b.co", password: "pw", tenant_slug: "acme" });
});

test("an off-site next is ignored", async () => {
  search = "next=%2F%2Fevil.test";
  routeFetch({ "POST /api/auth/login": () => Response.json({ ok: true }) });
  render(<LoginForm />);
  fill();
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/documents"));
});

test("wrong credentials show a clear message", async () => {
  routeFetch({ "POST /api/auth/login": () => Response.json({ code: "invalid_credentials" }, { status: 401 }) });
  render(<LoginForm />);
  fill();
  expect(await screen.findByRole("alert")).toHaveTextContent("Email, password or workspace is wrong.");
  expect(replace).not.toHaveBeenCalled();
});

test("429 shows Retry-After seconds; cold start shows the waking message", async () => {
  routeFetch({
    "POST /api/auth/login": () =>
      Response.json({ code: "rate_limited" }, { status: 429, headers: { "Retry-After": "30" } }),
  });
  const { unmount } = render(<LoginForm />);
  fill();
  expect(await screen.findByRole("alert")).toHaveTextContent("Try again in 30 seconds");
  unmount();

  routeFetch({ "POST /api/auth/login": () => Response.json({ code: "service_waking" }, { status: 503 }) });
  render(<LoginForm />);
  fill();
  expect(await screen.findByRole("alert")).toHaveTextContent("waking up");
});

test("demo button calls the demo route with no body and goes to the app", async () => {
  const f = routeFetch({ "POST /api/auth/demo": () => Response.json({ ok: true }) });
  render(<LoginForm demoAvailable />);
  expect(screen.getByText(/shared, read-only account/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Try the demo" }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/documents"));
  expect(f.calls[0]!.req.method).toBe("POST");
  expect(await f.calls[0]!.req.text()).toBe("");
});

