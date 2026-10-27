import { QueryClient } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";
import { demoLogin, login, logout } from "@/lib/api/client";
import { defaultAuthedDeps } from "@/lib/api/authed-fetch";
import { getQueryClient } from "@/lib/query/client";
import { routeFetch } from "@/test/fetch-mock";
import * as end from "./end";
import { COMPARE_QUERY_STORAGE, CONVERSATION_STORAGE } from "./storage";

test("endSessionState clears the query cache and both stored entries", () => {
  const client: QueryClient = getQueryClient();
  client.setQueryData(["compare", "vector", "q"], [{ x: 1 }]);
  sessionStorage.setItem(CONVERSATION_STORAGE, "11111111-1111-1111-1111-111111111111");
  sessionStorage.setItem(COMPARE_QUERY_STORAGE, "refunds");
  sessionStorage.setItem("unrelated", "kept");
  end.endSessionState();
  expect(client.getQueryData(["compare", "vector", "q"])).toBeUndefined();
  expect(sessionStorage.getItem(CONVERSATION_STORAGE)).toBeNull();
  expect(sessionStorage.getItem(COMPARE_QUERY_STORAGE)).toBeNull();
  expect(sessionStorage.getItem("unrelated")).toBe("kept");
});

test("endSessionState does not throw when storage is blocked", () => {
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(() => end.endSessionState()).not.toThrow();
  vi.restoreAllMocks();
});

function trace() {
  const order: string[] = [];
  vi.spyOn(end, "endSessionState").mockImplementation(() => void order.push("end"));
  return order;
}

test("login ends the previous session state before and after the request", async () => {
  const order = trace();
  routeFetch({ "POST /api/auth/login": () => (order.push("request"), Response.json({})) });
  await login({ email: "a@b.c", password: "x", tenant_slug: "t" });
  expect(order).toEqual(["end", "request", "end"]);
});

test("demo login ends the previous session state before and after the request", async () => {
  const order = trace();
  routeFetch({ "POST /api/auth/demo": () => (order.push("request"), Response.json({})) });
  await demoLogin();
  expect(order).toEqual(["end", "request", "end"]);
});

test("logout ends the session state before and after the request, also when it fails", async () => {
  const order = trace();
  routeFetch({ "POST /api/auth/logout": () => (order.push("request"), new Response(null, { status: 204 })) });
  await logout();
  expect(order).toEqual(["end", "request", "end"]);
  order.length = 0;
  vi.stubGlobal("fetch", () => Promise.reject(new Error("down")));
  await expect(logout()).rejects.toThrow();
  expect(order).toEqual(["end", "end"]);
});

test("an expired session ends the session state before the redirect", () => {
  const order = trace();
  const loc = { pathname: "/chat", search: "", set href(v: string) { order.push(`redirect ${v}`); } };
  vi.stubGlobal("location", loc);
  defaultAuthedDeps.endSession();
  expect(order).toEqual(["end", "redirect /login?next=%2Fchat"]);
});
