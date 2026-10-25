// @vitest-environment node
import { NextRequest } from "next/server";
import { expect, test } from "vitest";
import { proxy } from "./proxy";

test("no refresh cookie redirects to /login with next=", () => {
  const res = proxy(new NextRequest("http://app.test/documents?tab=2"));
  expect(res.status).toBe(307);
  expect(res.headers.get("location")).toBe("http://app.test/login?next=%2Fdocuments%3Ftab%3D2");
});

test("with the refresh cookie the page is served", () => {
  const res = proxy(new NextRequest("http://app.test/documents", { headers: { cookie: "hh_rt=x" } }));
  expect(res.headers.get("location")).toBeNull();
});
