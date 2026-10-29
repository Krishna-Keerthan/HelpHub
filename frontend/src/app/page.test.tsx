import type { ReactElement } from "react";
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const jar = vi.hoisted(() => ({ rt: undefined as string | undefined }));
const redirect = vi.hoisted(() => vi.fn((to: string) => { throw new Error(`REDIRECT ${to}`); }));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (n: string) => (n === "hh_rt" && jar.rt ? { name: n, value: jar.rt } : undefined) }) }));
vi.mock("next/navigation", () => ({ redirect, useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/" }));
vi.mock("@/lib/server/auth-handlers", () => ({ missingDemoVars: () => [] }));

import Home, { metadata } from "./page";
import { FAQ } from "@/components/home/Faq";
import { FEATURES } from "@/components/home/Features";

beforeEach(() => {
  jar.rt = undefined;
  redirect.mockClear();
  vi.unstubAllEnvs();
  vi.stubEnv("NEXT_PUBLIC_CONTACT_EMAIL", "beta@example.test");
});
afterEach(() => vi.useRealTimers());

const page = async () => render((await Home()) as ReactElement);

test("a signed-in visitor (hh_rt) is sent to /documents", async () => {
  jar.rt = "token";
  await expect(Home()).rejects.toThrow("REDIRECT /documents");
  expect(redirect).toHaveBeenCalledWith("/documents");
});

test("hero: badge, headline, both actions, demo caption, cold-start line, mock chat, no screenshots", async () => {
  await page();
  expect(screen.getByText("Closed beta")).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Answers from your own support documents");
  expect(screen.getByRole("button", { name: "Try the demo" })).toBeEnabled();
  expect(screen.getByText(/shared, read-only account; do not enter personal information/)).toBeInTheDocument();
  expect(screen.getByText(/The free tier sleeps when idle, so the first request can take about a minute/)).toBeInTheDocument();
  expect(screen.getByTestId("mock-chat")).toHaveAttribute("aria-hidden", "true");
  expect(screen.queryAllByRole("img")).toHaveLength(0);
});

test("not-found claims are no stronger than the measured gate behaviour", async () => {
  await page();
  const claim = /Unrelated questions are refused/;
  const near = /answer built from the nearest passages/;
  expect(screen.getByRole("heading", { level: 1 }).parentElement).toHaveTextContent(claim);
  expect(screen.getByRole("heading", { level: 1 }).parentElement).toHaveTextContent(near);
  expect(document.getElementById("features")).toHaveTextContent(claim);
  expect(document.getElementById("features")).toHaveTextContent(near);
  expect(document.getElementById("faq")).toHaveTextContent(claim);
  expect(document.getElementById("faq")).toHaveTextContent(near);
  expect(document.body).not.toHaveTextContent(/instead of guessing/);
});

test("navbar: wordmark, anchors to the sections, theme toggle, Sign in and Request access", async () => {
  await page();
  const header = screen.getByRole("banner");
  expect(within(header).getByText("HelpHub")).toBeInTheDocument();
  expect(within(header).getByRole("link", { name: "Features" })).toHaveAttribute("href", "#features");
  expect(within(header).getByRole("link", { name: "FAQ" })).toHaveAttribute("href", "#faq");
  expect(within(header).getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  expect(within(header).getByRole("link", { name: "Request access" })).toHaveAttribute("href", expect.stringContaining("mailto:beta@example.test"));
  expect(within(header).getByRole("button", { name: /theme/i })).toBeInTheDocument();
});

test("features section has an id and one card per verified feature", async () => {
  await page();
  const section = document.getElementById("features")!;
  expect(within(section).getByRole("heading", { level: 2 })).toBeInTheDocument();
  expect(within(section).getAllByRole("listitem")).toHaveLength(FEATURES.length);
  expect(FEATURES.length).toBe(7);
});

test("FAQ is native <details>, 5 to 7 of them, none open by default", async () => {
  await page();
  const items = document.getElementById("faq")!.querySelectorAll("details");
  expect(items).toHaveLength(FAQ.length);
  expect(items.length).toBeGreaterThanOrEqual(5);
  expect(items.length).toBeLessThanOrEqual(7);
  for (const d of items) {
    expect(d.hasAttribute("open")).toBe(false);
    expect(d.querySelector("summary")).not.toBeNull();
  }
});

test("FAQ states the real upload limits", async () => {
  await page();
  const faq = document.getElementById("faq")!;
  expect(faq).toHaveTextContent("4 MB");
  expect(faq).toHaveTextContent("500,000");
});

test("footer: credit, current year, GitHub link that opens safely, Contact link", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2031-06-15T00:00:00Z"));
  await page();
  const footer = screen.getByRole("contentinfo");
  expect(footer).toHaveTextContent("Built by Krishna Keerthan K");
  expect(footer).toHaveTextContent("© 2031 Krishna Keerthan K. All rights reserved.");
  const gh = within(footer).getByRole("link", { name: "GitHub" });
  expect(gh).toHaveAttribute("href", "https://github.com/Krishna-Keerthan/HelpHub");
  expect(gh).toHaveAttribute("target", "_blank");
  expect(gh.getAttribute("rel")).toBe("noopener noreferrer");
  expect(within(footer).getByRole("link", { name: "Contact" })).toHaveAttribute("href", "mailto:beta@example.test");
});

test.each([undefined, "", "  "])("with the contact email %j, Request access and Contact are hidden, the rest renders", async (value) => {
  vi.stubEnv("NEXT_PUBLIC_CONTACT_EMAIL", value as string);
  await page();
  expect(screen.queryByRole("link", { name: "Request access" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Contact" })).toBeNull();
  expect(screen.getAllByRole("link", { name: "Sign in" }).length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: "Try the demo" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "GitHub" })).toBeInTheDocument();
});

test("page metadata has a title and description", () => {
  expect(metadata.title).toBeTruthy();
  expect(String(metadata.description)).toMatch(/cites its sources/);
});
