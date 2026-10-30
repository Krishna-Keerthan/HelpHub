import { afterEach, describe, expect, test, vi } from "vitest";
import { createAuthedFetch, defaultAuthedDeps, type AuthedFetchDeps } from "./authed-fetch";

const expired = () => Response.json({ code: "token_expired" }, { status: 401 });
const okRes = () => Response.json({ ok: true });

function make(fetchImpl: AuthedFetchDeps["fetch"], outcome: Awaited<ReturnType<AuthedFetchDeps["refresh"]>>) {
  const refresh = vi.fn(async () => outcome);
  const endSession = vi.fn();
  const f = createAuthedFetch({ fetch: fetchImpl, refresh, now: () => 1, endSession });
  return { f, refresh, endSession };
}
const request = () => new Request("http://app.test/api/documents", { method: "POST", body: "payload" });

describe("createAuthedFetch", () => {
  test("token_expired -> refresh once -> retry once with the same body", async () => {
    const calls: string[] = [];
    const fetchImpl = vi.fn(async (r: Request | string | URL) => {
      const req = r as Request;
      calls.push(await req.text());
      return calls.length === 1 ? expired() : okRes();
    }) as unknown as AuthedFetchDeps["fetch"];
    const { f, refresh } = make(fetchImpl, "ok");
    const res = await f(request());
    expect(res.status).toBe(200);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(calls).toEqual(["payload", "payload"]);
  });

  test("no loop: a second token_expired is returned and refresh is not called again", async () => {
    const fetchImpl = vi.fn(async () => expired()) as unknown as AuthedFetchDeps["fetch"];
    const { f, refresh, endSession } = make(fetchImpl, "ok");
    const res = await f(request());
    expect(res.status).toBe(401);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(endSession).not.toHaveBeenCalled();
  });

  test("refresh rejected (expired / reuse revoked) ends the session without retrying", async () => {
    const fetchImpl = vi.fn(async () => expired()) as unknown as AuthedFetchDeps["fetch"];
    const { f, endSession } = make(fetchImpl, "expired");
    await f(request());
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(endSession).toHaveBeenCalledTimes(1);
  });

  test("cold start: 503 service_waking, session NOT ended", async () => {
    const fetchImpl = vi.fn(async () => expired()) as unknown as AuthedFetchDeps["fetch"];
    const { f, endSession } = make(fetchImpl, "waking");
    const res = await f(request());
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ code: "service_waking" });
    expect(endSession).not.toHaveBeenCalled();
  });

  test("a plain 401 (not token_expired) is passed through without refreshing", async () => {
    const fetchImpl = vi.fn(async () => Response.json({ code: "invalid_credentials" }, { status: 401 })) as unknown as AuthedFetchDeps["fetch"];
    const { f, refresh } = make(fetchImpl, "ok");
    expect((await f(request())).status).toBe(401);
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("defaultAuthedDeps.endSession", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("a session that ends on its own goes to /login with next and reason=expired", () => {
    const loc = { pathname: "/chat", search: "?c=1", href: "" };
    vi.stubGlobal("location", loc);
    defaultAuthedDeps.endSession();
    expect(loc.href).toBe("/login?next=%2Fchat%3Fc%3D1&reason=expired");
  });
});
