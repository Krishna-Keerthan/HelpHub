import { NextRequest } from "next/server";
import type { Deps } from "@/lib/server/upstream";

export const BACKEND = "http://backend.test";
export const ORIGIN = "http://app.test";

function b64url(o: object): string {
  return btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** Unsigned JWT-shaped token; the BFF only reads `exp`. */
export function fakeJwt(expSeconds: number, tag = "x"): string {
  return `${b64url({ alg: "none" })}.${b64url({ exp: expSeconds, tag })}.sig`;
}

export const inMinutes = (m: number) => Math.floor(Date.now() / 1000) + m * 60;

export function req(
  path: string,
  init: { method?: string; cookies?: Record<string, string>; origin?: string | null; body?: BodyInit; base?: string } = {},
): NextRequest {
  const headers = new Headers();
  if (init.origin !== null) headers.set("origin", init.origin ?? ORIGIN);
  if (init.cookies) {
    headers.set("cookie", Object.entries(init.cookies).map(([k, v]) => `${k}=${v}`).join("; "));
  }
  return new NextRequest(`${init.base ?? ORIGIN}${path}`, { method: init.method ?? "POST", headers, body: init.body });
}

export const noSleep: Deps["sleep"] = async () => {};

/**
 * In-memory stand-in for the backend auth rules: refresh rotates on every use and a
 * reused token revokes the whole family.
 */
export function fakeBackend() {
  const log: string[] = [];
  let seq = 0;
  const used = new Set<string>();
  let revoked = false;
  let current = "rt-0";
  let healthy = true;
  let refreshBehaviour: "normal" | "throw" | "500" = "normal";

  const fetchImpl: typeof fetch = async (input, init) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
    log.push(`${init?.method ?? "GET"} ${url.pathname}`);
    if (url.pathname === "/health") {
      return healthy ? new Response("{}", { status: 200 }) : new Response("", { status: 503 });
    }
    if (url.pathname === "/auth/refresh") {
      if (refreshBehaviour === "throw") throw new TypeError("socket hang up");
      if (refreshBehaviour === "500") return new Response("", { status: 500 });
      const { refresh_token } = JSON.parse(String(init?.body)) as { refresh_token: string };
      if (revoked || used.has(refresh_token) || refresh_token !== current) {
        if (used.has(refresh_token)) revoked = true; // reuse detected: family revoked
        return Response.json({ detail: "bad" }, { status: 401 });
      }
      used.add(refresh_token);
      current = `rt-${++seq}`;
      return Response.json({ access_token: fakeJwt(inMinutes(15), current), refresh_token: current });
    }
    return new Response("{}", { status: 404 });
  };

  return {
    deps: { fetch: fetchImpl, sleep: noSleep } satisfies Deps,
    log,
    refreshCalls: () => log.filter((l) => l === "POST /auth/refresh").length,
    get current() { return current; },
    get revoked() { return revoked; },
    setHealthy(v: boolean) { healthy = v; },
    setRefresh(b: "normal" | "throw" | "500") { refreshBehaviour = b; },
  };
}
