// @vitest-environment node
import { beforeEach, expect, test, vi } from "vitest";
import { isExpired } from "./jwt";
import { originAllowed } from "./origin";
import { wakeBackend } from "./upstream";
import { BACKEND, fakeBackend, fakeJwt, inMinutes, req } from "@/test/helpers";

beforeEach(() => vi.stubEnv("BACKEND_URL", BACKEND));

test("wakeBackend retries a slow cold start and stops once healthy", async () => {
  let n = 0;
  const sleep = vi.fn(async () => {});
  const fetchImpl = (async () => (++n < 3 ? new Response("", { status: 503 }) : new Response("{}"))) as typeof fetch;
  expect(await wakeBackend({ fetch: fetchImpl, sleep })).toBe(true);
  expect(n).toBe(3);
  expect(sleep).toHaveBeenCalledTimes(2);
});

test("wakeBackend is bounded", async () => {
  const be = fakeBackend();
  be.setHealthy(false);
  expect(await wakeBackend(be.deps)).toBe(false);
  expect(be.log).toHaveLength(4);
});

test("isExpired: past exp, near exp, unreadable token", () => {
  const now = Date.now();
  expect(isExpired(fakeJwt(inMinutes(10)), now)).toBe(false);
  expect(isExpired(fakeJwt(inMinutes(-1)), now)).toBe(true);
  expect(isExpired(fakeJwt(Math.floor(now / 1000) + 2), now)).toBe(true);
  expect(isExpired("garbage", now)).toBe(true);
});

test("originAllowed: safe methods pass, same origin and listed origins pass, others fail", () => {
  expect(originAllowed(req("/x", { method: "GET", origin: null }), [])).toBe(true);
  expect(originAllowed(req("/x"), [])).toBe(true);
  expect(originAllowed(req("/x", { origin: "https://app.vercel.app" }), ["https://app.vercel.app"])).toBe(true);
  expect(originAllowed(req("/x", { origin: "https://evil.test" }), [])).toBe(false);
  expect(originAllowed(req("/x", { origin: null }), [])).toBe(false);
});
