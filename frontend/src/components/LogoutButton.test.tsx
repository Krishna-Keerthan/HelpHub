import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { routeFetch } from "@/test/fetch-mock";
import { LogoutButton } from "./LogoutButton";

afterEach(() => vi.unstubAllGlobals());

function stubLocation() {
  const assign = vi.fn();
  vi.stubGlobal("location", { ...window.location, assign });
  return assign;
}

test("logging out sends the user to /login", async () => {
  const f = routeFetch({ "POST /api/auth/logout": () => new Response(null, { status: 204 }) });
  const assign = stubLocation();
  render(<LogoutButton />);
  fireEvent.click(screen.getByRole("button", { name: "Log out" }));
  await waitFor(() => expect(assign).toHaveBeenCalledWith("/login"));
  expect(f.keys()).toEqual(["POST /api/auth/logout"]);
});

test("if the logout request throws, the user is still sent to /login (and nothing is left unhandled)", async () => {
  routeFetch({
    "POST /api/auth/logout": () => {
      throw new TypeError("offline");
    },
  });
  const unhandled = vi.fn();
  process.on("unhandledRejection", unhandled);
  const assign = stubLocation();
  render(<LogoutButton />);
  fireEvent.click(screen.getByRole("button", { name: "Log out" }));
  await waitFor(() => expect(assign).toHaveBeenCalledWith("/login"));
  await new Promise((r) => setTimeout(r, 20));
  process.off("unhandledRejection", unhandled);
  expect(unhandled).not.toHaveBeenCalled();
});
