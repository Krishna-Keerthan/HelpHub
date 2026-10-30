import type { Metadata } from "next";
import { expect, test, vi } from "vitest";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => undefined }) }));
vi.mock("next/font/google", () => ({ Inter: () => ({ variable: "inter-var" }) }));
vi.mock("./globals.css", () => ({}));
vi.mock("@/lib/server/auth-handlers", () => ({ missingDemoVars: () => [] }));

import { metadata as root, viewport } from "./layout";
import { metadata as chat } from "./(app)/chat/page";
import { metadata as compare } from "./(app)/compare/page";
import { metadata as documents } from "./(app)/documents/page";
import { metadata as users } from "./(app)/users/page";
import { metadata as login } from "./login/page";
import { metadata as home } from "./page";
import { metadata as homeRoute } from "./home/page";

test("root title has a default and a template that appends the site name", () => {
  expect(root.title).toEqual({ default: "HelpHub", template: "%s · HelpHub" });
});

test.each([
  ["login", login, "Sign in"],
  ["documents", documents, "Documents"],
  ["chat", chat, "Chat"],
  ["compare", compare, "Compare retrieval"],
  ["users", users, "Users"],
] as [string, Metadata, string][])("%s has its own title and a one-line description", (_n, m, title) => {
  expect(m.title).toBe(title);
  expect(String(m.description).length).toBeGreaterThan(10);
  expect(String(m.description)).not.toContain("\n");
});

test("the five page titles are all different", () => {
  const titles = [login, documents, chat, compare, users].map((m) => m.title);
  expect(new Set(titles).size).toBe(5);
});

test("the home page keeps its full headline without the template suffix, on / and /home", () => {
  expect(home.title).toEqual({ absolute: "HelpHub: answers from your support documents" });
  expect(homeRoute).toBe(home);
});

test("Open Graph and Twitter carry text only: no image, no guessed base URL", () => {
  expect(root.openGraph).toMatchObject({ title: "HelpHub", siteName: "HelpHub" });
  expect(root.twitter).toMatchObject({ card: "summary", title: "HelpHub" });
  expect(root.openGraph).not.toHaveProperty("images");
  expect(root.twitter).not.toHaveProperty("images");
  expect(root.metadataBase).toBeUndefined();
});

test("viewport sets a light and a dark theme colour", () => {
  expect(viewport.themeColor).toEqual([
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#111113" },
  ]);
});
