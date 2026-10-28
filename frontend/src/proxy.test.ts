// @vitest-environment node
import { NextRequest } from "next/server";
import { expect, test } from "vitest";
import { config, proxy } from "./proxy";

test("no refresh cookie redirects to /login with next=", () => {
  const res = proxy(new NextRequest("http://app.test/documents?tab=2"));
  expect(res.status).toBe(307);
  expect(res.headers.get("location")).toBe("http://app.test/login?next=%2Fdocuments%3Ftab%3D2");
});

test("with the refresh cookie the page is served", () => {
  const res = proxy(new NextRequest("http://app.test/documents", { headers: { cookie: "hh_rt=x" } }));
  expect(res.headers.get("location")).toBeNull();
});

test("the home page is public without a cookie", () => {
  const res = proxy(new NextRequest("http://app.test/"));
  expect(res.headers.get("location")).toBeNull();
});

test("only the exact home path is public", () => {
  for (const path of ["/documents", "/users", "/chat", "/homepage"]) {
    const res = proxy(new NextRequest(`http://app.test${path}`));
    expect(res.headers.get("location"), path).toBe(`http://app.test/login?next=${encodeURIComponent(path)}`);
  }
});

test("the matcher covers the home page and protected pages, and leaves static assets and the API alone", () => {
  const re = new RegExp(`^${config.matcher[0]}$`);
  expect(re.test("/")).toBe(true);
  expect(re.test("/documents")).toBe(true);
  expect(re.test("/home/chat-dark.png")).toBe(true); // no public image path any more: it is protected like any page
  expect(re.test("/_next/static/x.js")).toBe(false);
  expect(re.test("/api/documents")).toBe(false);
});
