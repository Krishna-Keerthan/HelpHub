import type { ReactElement } from "react";
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const jar = vi.hoisted(() => ({ rt: undefined as string | undefined }));
const redirect = vi.hoisted(() => vi.fn((to: string) => { throw new Error(`REDIRECT ${to}`); }));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (n: string) => (n === "hh_rt" && jar.rt ? { name: n, value: jar.rt } : undefined) }) }));
vi.mock("next/navigation", () => ({ redirect, useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/" }));
vi.mock("@/lib/server/auth-handlers", () => ({ missingDemoVars: () => [] }));

import Home, { } from "./page";
import HomeRoute from "./home/page";
beforeEach(() => {
  jar.rt = undefined;
  redirect.mockClear();
  vi.unstubAllEnvs();
  vi.stubEnv("NEXT_PUBLIC_CONTACT_EMAIL", "beta@example.test");
});
afterEach(() => vi.useRealTimers());

const homeRoute = async () => render((await HomeRoute()) as ReactElement);

test("a signed-in visitor (hh_rt) is sent to /documents", async () => {
  jar.rt = "token";
  await expect(Home()).rejects.toThrow("REDIRECT /documents");
  expect(redirect).toHaveBeenCalledWith("/documents");
});

test("/home renders for a signed-in visitor with Open the app in the nav and the hero, and no redirect", async () => {
  jar.rt = "token";
  await homeRoute();
  expect(redirect).not.toHaveBeenCalled();
  for (const region of [screen.getByRole("banner"), screen.getByRole("main")]) {
    expect(within(region).getByRole("link", { name: "Open the app" })).toHaveAttribute("href", "/documents");
  }
  expect(screen.queryByRole("link", { name: "Sign in" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Try the demo" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Request access" })).toBeNull();
});

