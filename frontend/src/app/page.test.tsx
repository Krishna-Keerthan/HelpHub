import type { ReactElement } from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const jar = vi.hoisted(() => ({ rt: undefined as string | undefined }));
const redirect = vi.hoisted(() => vi.fn((to: string) => { throw new Error(`REDIRECT ${to}`); }));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (n: string) => (n === "hh_rt" && jar.rt ? { name: n, value: jar.rt } : undefined) }) }));
vi.mock("next/navigation", () => ({ redirect, useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/" }));
vi.mock("@/lib/server/auth-handlers", () => ({ missingDemoVars: () => [] }));

import Home, { metadata } from "./page";

beforeEach(() => {
  jar.rt = undefined;
  redirect.mockClear();
  vi.unstubAllEnvs();
});

test("a signed-in visitor (hh_rt) is sent to /documents", async () => {
  jar.rt = "token";
  await expect(Home()).rejects.toThrow("REDIRECT /documents");
  expect(redirect).toHaveBeenCalledWith("/documents");
});

test("a visitor sees the pitch, both calls to action, the badge, the cold-start line and three screenshots", async () => {
  vi.stubEnv("NEXT_PUBLIC_CONTACT_EMAIL", "beta@example.test");
  render((await Home()) as ReactElement);
  expect(screen.getByRole("button", { name: "Try the demo" })).toBeEnabled();
  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  expect(screen.getByText("Closed beta")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Request access" })).toHaveAttribute("href", expect.stringContaining("mailto:beta@example.test"));
  expect(screen.getByText(/about a minute/)).toBeInTheDocument();
  expect(screen.getByText(/cites the passages/)).toBeInTheDocument();
  const imgs = screen.getAllByRole("img");
  expect(imgs).toHaveLength(3);
  for (const img of imgs) expect(img.getAttribute("alt")).toMatch(/.{30,}/);
  expect(redirect).not.toHaveBeenCalled();
});

test("without NEXT_PUBLIC_CONTACT_EMAIL the request link is absent and the rest still renders", async () => {
  vi.stubEnv("NEXT_PUBLIC_CONTACT_EMAIL", "");
  render((await Home()) as ReactElement);
  expect(screen.queryByRole("link", { name: "Request access" })).toBeNull();
  expect(screen.getByRole("button", { name: "Try the demo" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
});

test("page metadata has a title and description", () => {
  expect(metadata.title).toBeTruthy();
  expect(String(metadata.description)).toMatch(/cites its sources/);
});
