// @vitest-environment node
import { beforeEach, describe, expect, test, vi } from "vitest";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "./cookies";
import { eventCount } from "./events";
import { handleLogin, handleLogout, handleRefresh } from "./auth-handlers";
import { createAuthedFetch } from "../api/authed-fetch";
import { refreshWithBackoff, resetSessionForTests, type SessionDeps } from "../api/session";
import { BACKEND, fakeBackend, fakeJwt, inMinutes, req } from "@/test/helpers";

beforeEach(() => {
  vi.stubEnv("BACKEND_URL", BACKEND);
  resetSessionForTests();
});

const cookiesOf = (res: Response) => res.headers.getSetCookie();
const cleared = (res: Response) =>
  [ACCESS_COOKIE, REFRESH_COOKIE].every((n) =>
    cookiesOf(res).some((c) => c.startsWith(`${n}=;`) && /Max-Age=0/i.test(c)),
  );

describe("handleRefresh", () => {
  test("success rotates both cookies: httpOnly, SameSite=Lax, not Secure on http localhost", async () => {
    const be = fakeBackend();
    const res = await handleRefresh(
      req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: "rt-0" }, base: "http://localhost:3000", origin: "http://localhost:3000" }),
      be.deps,
    );
    expect(res.status).toBe(200);
    const set = cookiesOf(res);
    expect(set.find((c) => c.startsWith(`${REFRESH_COOKIE}=rt-1`))).toMatch(/HttpOnly/i);
    expect(set.some((c) => /Secure/i.test(c))).toBe(false);
    for (const c of set) {
      expect(c).toMatch(/SameSite=lax/i);
      expect(c).toMatch(/Path=\//);
    }
    expect(be.refreshCalls()).toBe(1);
  });

  test("Secure is set when not plain-http localhost", async () => {
    const be = fakeBackend();
    const r = req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: "rt-0" } }); // http://app.test
    const res = await handleRefresh(r, be.deps);
    expect(cookiesOf(res).every((c) => /Secure/i.test(c) === true)).toBe(true);
  });

  test("backend 401 (reuse / revoked) clears the cookies", async () => {
    const be = fakeBackend();
    const res = await handleRefresh(req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: "stale" } }), be.deps);
    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ code: "session_expired" });
    expect(cleared(res)).toBe(true);
  });

  test("cold start: backend never wakes -> 503, cookies untouched, refresh token never sent", async () => {
    const be = fakeBackend();
    be.setHealthy(false);
    const res = await handleRefresh(req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: "rt-0" } }), be.deps);
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ code: "service_waking" });
    expect(cookiesOf(res)).toEqual([]);
    expect(be.refreshCalls()).toBe(0);
    expect(be.log.filter((l) => l === "GET /health")).toHaveLength(4); // bounded wake-up
  });

  test("token sent but the answer is lost or 5xx -> 502 indeterminate, cookies untouched, sent once", async () => {
    for (const mode of ["throw", "500"] as const) {
      const be = fakeBackend();
      be.setRefresh(mode);
      const res = await handleRefresh(req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: "rt-0" } }), be.deps);
      expect(res.status).toBe(502);
      expect(cookiesOf(res)).toEqual([]);
      expect(be.refreshCalls()).toBe(1);
    }
  });

  test("no refresh cookie -> 401 no_session without calling the backend", async () => {
    const be = fakeBackend();
    const res = await handleRefresh(req("/api/auth/refresh"), be.deps);
    expect(res.status).toBe(401);
    expect(be.log).toEqual([]);
  });

  test("foreign or missing Origin -> 403, backend untouched", async () => {
    const be = fakeBackend();
    for (const origin of ["http://evil.test", null]) {
      const res = await handleRefresh(
        req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: "rt-0" }, origin }),
        be.deps,
      );
      expect(res.status).toBe(403);
    }
    expect(be.log).toEqual([]);
  });
});

describe("reuse scenario", () => {
  const sessionDeps = (be: ReturnType<typeof fakeBackend>, jar: { rt: string }): SessionDeps => {
    let stamp = 0;
    return {
      post: async () => {
        const res = await handleRefresh(req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: jar.rt } }), be.deps);
        const next = cookiesOf(res).find((c) => c.startsWith(`${REFRESH_COOKIE}=`));
        const value = next?.split(";")[0]?.split("=")[1];
        if (value) jar.rt = value; // the browser stores the rotated cookie
        return res;
      },
      now: () => 10,
      sleep: async () => {},
      withLock: (fn) => fn(),
      readStamp: () => stamp,
      writeStamp: (m) => (stamp = m),
    };
  };

  test("parallel 401s through the single-flight cause ONE rotation; the family survives", async () => {
    const be = fakeBackend();
    const jar = { rt: "rt-0" };
    const d = sessionDeps(be, jar);
    const results = await Promise.all(Array.from({ length: 6 }, () => refreshWithBackoff(0, () => {}, d)));
    expect(results).toEqual(Array(6).fill("ok"));
    expect(be.refreshCalls()).toBe(1);
    expect(be.revoked).toBe(false);
    expect(jar.rt).toBe("rt-1");
  });

  test("without coordination the same token twice IS reuse: family revoked, session ends, no retry loop", async () => {
    const be = fakeBackend();
    const first = await handleRefresh(req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: "rt-0" } }), be.deps);
    const second = await handleRefresh(req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: "rt-0" } }), be.deps);
    expect(first.status).toBe(200);
    expect(second.status).toBe(401);
    expect(be.revoked).toBe(true);
    expect(cleared(second)).toBe(true);

    // Even the freshly issued token is now dead, so the user must log in again.
    const third = await handleRefresh(req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: "rt-1" } }), be.deps);
    expect(third.status).toBe(401);

    // Client side: refresh answers 401 -> session ends once, request not retried.
    const jar = { rt: "rt-0" };
    const endSession = vi.fn();
    const fetchImpl = vi.fn(async () => Response.json({ code: "token_expired" }, { status: 401 }));
    const f = createAuthedFetch({
      fetch: fetchImpl as unknown as typeof fetch,
      refresh: (sentAt, onWaking) => refreshWithBackoff(sentAt, onWaking, sessionDeps(be, jar)),
      now: () => 1,
      endSession,
    });
    resetSessionForTests();
    await f(new Request("http://app.test/api/documents"));
    expect(endSession).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});

describe("handleLogin / handleLogout", () => {
  test("login sets cookies on success and maps 401 to invalid_credentials without cookies", async () => {
    const pair = { access_token: fakeJwt(inMinutes(15)), refresh_token: "rt-9" };
    let status = 200;
    const deps = {
      sleep: async () => {},
      fetch: (async (input: RequestInfo | URL) => {
        const path = new URL(String(input)).pathname;
        if (path === "/health") return new Response("{}");
        return status === 200 ? Response.json(pair) : Response.json({ detail: "x" }, { status });
      }) as typeof fetch,
    };
    const body = JSON.stringify({ email: "a@b.co", password: "pw", tenant_slug: "t" });
    const ok = await handleLogin(req("/api/auth/login", { body }), deps);
    expect(ok.status).toBe(200);
    expect(cookiesOf(ok)).toHaveLength(2);
    status = 401;
    const bad = await handleLogin(req("/api/auth/login", { body }), deps);
    expect(bad.status).toBe(401);
    expect(await bad.json()).toEqual({ code: "invalid_credentials" });
    expect(cookiesOf(bad)).toEqual([]);
  });

  test("logout sends only the refresh token in the body, with no Bearer, even without an access cookie", async () => {
    const calls: { url: string; headers: Headers; body: string }[] = [];
    const deps = {
      sleep: async () => {},
      fetch: (async (input: RequestInfo | URL, init?: RequestInit) => {
        calls.push({ url: String(input), headers: new Headers(init?.headers), body: String(init?.body) });
        return new Response(null, { status: 204 });
      }) as typeof fetch,
    };
    const res = await handleLogout(req("/api/auth/logout", { cookies: { [REFRESH_COOKIE]: "rt-0" } }), deps);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ sent: true });
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe(`${BACKEND}/auth/logout`);
    expect(calls[0]!.headers.get("authorization")).toBeNull();
    expect(JSON.parse(calls[0]!.body)).toEqual({ refresh_token: "rt-0" });
    expect(cleared(res)).toBe(true);
  });

  test("an expired access cookie does not matter: logout still reaches the backend", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 }));
    const res = await handleLogout(
      req("/api/auth/logout", { cookies: { [REFRESH_COOKIE]: "rt-0", [ACCESS_COOKIE]: fakeJwt(inMinutes(-30)) } }),
      { sleep: async () => {}, fetch: fetchImpl as unknown as typeof fetch },
    );
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(await res.json()).toEqual({ sent: true });
  });

  test("backend down or non-204: cookies are still cleared, sent is false", async () => {
    for (const fetchImpl of [
      (async () => { throw new TypeError("down"); }) as typeof fetch,
      (async () => new Response("", { status: 500 })) as typeof fetch,
    ]) {
      const res = await handleLogout(
        req("/api/auth/logout", { cookies: { [REFRESH_COOKIE]: "rt-0" } }),
        { sleep: async () => {}, fetch: fetchImpl },
      );
      expect(res.status).toBe(200);
      expect(await res.json()).toEqual({ sent: false });
      expect(cleared(res)).toBe(true);
    }
  });

  test("no refresh cookie: nothing is sent, cookies cleared", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 }));
    const res = await handleLogout(req("/api/auth/logout"), { sleep: async () => {}, fetch: fetchImpl as unknown as typeof fetch });
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(await res.json()).toEqual({ sent: false });
    expect(cleared(res)).toBe(true);
  });

  test("logout rejects a foreign origin", async () => {
    const res = await handleLogout(req("/api/auth/logout", { origin: "http://evil.test" }));
    expect(res.status).toBe(403);
  });
});

describe("auth event counters", () => {
  test("indeterminate and forced-logout reasons are counted and logged without tokens", async () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => {});
    const before = {
      ind: eventCount("refresh_indeterminate", "network_or_timeout"),
      rej: eventCount("forced_logout", "refresh_rejected"),
      none: eventCount("forced_logout", "no_session"),
    };
    const lost = fakeBackend();
    lost.setRefresh("throw");
    await handleRefresh(req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: "rt-secret-0" } }), lost.deps);
    await handleRefresh(req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: "stale-secret" } }), fakeBackend().deps);
    await handleRefresh(req("/api/auth/refresh"), fakeBackend().deps);
    expect(eventCount("refresh_indeterminate", "network_or_timeout")).toBe(before.ind + 1);
    expect(eventCount("forced_logout", "refresh_rejected")).toBe(before.rej + 1);
    expect(eventCount("forced_logout", "no_session")).toBe(before.none + 1);
    const lines = info.mock.calls.map((c) => String(c[0]));
    expect(lines.some((l) => l.includes('"metric":"refresh_indeterminate"'))).toBe(true);
    expect(lines.join("\n")).not.toMatch(/secret|rt-0/);
    info.mockRestore();
  });

  test("waking (token never sent) is not counted as indeterminate or forced logout", async () => {
    const be = fakeBackend();
    be.setHealthy(false);
    const before = eventCount("refresh_indeterminate", "network_or_timeout") + eventCount("forced_logout", "refresh_rejected");
    await handleRefresh(req("/api/auth/refresh", { cookies: { [REFRESH_COOKIE]: "rt-0" } }), be.deps);
    expect(eventCount("refresh_indeterminate", "network_or_timeout") + eventCount("forced_logout", "refresh_rejected")).toBe(before);
  });
});
