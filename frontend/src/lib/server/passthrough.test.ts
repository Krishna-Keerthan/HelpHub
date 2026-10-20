// @vitest-environment node
import { beforeEach, describe, expect, test, vi } from "vitest";
import { ACCESS_COOKIE } from "./cookies";
import { passthrough } from "./passthrough";
import { BACKEND, fakeJwt, inMinutes, noSleep, req } from "@/test/helpers";

beforeEach(() => vi.stubEnv("BACKEND_URL", BACKEND));

const valid = () => ({ [ACCESS_COOKIE]: fakeJwt(inMinutes(10)) });
const spy = (impl: (url: string, init?: RequestInit) => Response | Promise<Response>) =>
  vi.fn(async (u: RequestInfo | URL, i?: RequestInit) => impl(String(u), i));

describe("passthrough", () => {
  test("forwards with Bearer from the cookie and never refreshes on its own", async () => {
    const fetchImpl = spy(() => Response.json([{ id: 1 }]));
    const cookies = valid();
    const res = await passthrough(req("/api/documents?x=1", { method: "GET", cookies }), ["documents"], {
      fetch: fetchImpl as unknown as typeof fetch,
      sleep: noSleep,
    });
    expect(res.status).toBe(200);
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(String(url)).toBe(`${BACKEND}/documents?x=1`);
    expect((init!.headers as Headers).get("authorization")).toBe(`Bearer ${cookies[ACCESS_COOKIE]}`);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  test("missing or expired access cookie -> token_expired without calling upstream", async () => {
    const fetchImpl = spy(() => Response.json({}));
    const deps = { fetch: fetchImpl as unknown as typeof fetch, sleep: noSleep };
    const cases: Record<string, string>[] = [{}, { [ACCESS_COOKIE]: fakeJwt(inMinutes(-1)) }];
    for (const cookies of cases) {
      const res = await passthrough(req("/api/documents", { method: "GET", cookies }), ["documents"], deps);
      expect(res.status).toBe(401);
      expect(await res.json()).toEqual({ code: "token_expired" });
    }
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  test("upstream 401 becomes token_expired (backend has no distinguishing signal)", async () => {
    const fetchImpl = spy(() => Response.json({ detail: "Not authenticated" }, { status: 401 }));
    const res = await passthrough(req("/api/documents", { method: "GET", cookies: valid() }), ["documents"], {
      fetch: fetchImpl as unknown as typeof fetch,
      sleep: noSleep,
    });
    expect(await res.json()).toEqual({ code: "token_expired" });
  });

  test("paths outside the allow-list are not forwarded (no /auth/login, /auth/refresh)", async () => {
    const fetchImpl = spy(() => Response.json({}));
    const deps = { fetch: fetchImpl as unknown as typeof fetch, sleep: noSleep };
    for (const seg of [["auth", "refresh"], ["auth", "login"], ["health"]]) {
      const res = await passthrough(req(`/api/${seg.join("/")}`, { cookies: valid() }), seg, deps);
      expect(res.status).toBe(404);
    }
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  test("state-changing requests need a same-origin Origin", async () => {
    const fetchImpl = spy(() => new Response(null, { status: 204 }));
    const deps = { fetch: fetchImpl as unknown as typeof fetch, sleep: noSleep };
    const bad = await passthrough(
      req("/api/documents/1", { method: "DELETE", cookies: valid(), origin: "http://evil.test" }),
      ["documents", "1"],
      deps,
    );
    expect(bad.status).toBe(403);
    const none = await passthrough(
      req("/api/documents/1", { method: "DELETE", cookies: valid(), origin: null }),
      ["documents", "1"],
      deps,
    );
    expect(none.status).toBe(403);
    expect(fetchImpl).not.toHaveBeenCalled();
    const good = await passthrough(req("/api/documents/1", { method: "DELETE", cookies: valid() }), ["documents", "1"], deps);
    expect(good.status).toBe(204);
  });

  test("streams the upstream body through (SSE) with no-store headers", async () => {
    const fetchImpl = spy(
      () => new Response("event: token\ndata: {}\n\n", { headers: { "content-type": "text/event-stream" } }),
    );
    const res = await passthrough(
      req("/api/chat/stream", { cookies: valid(), body: JSON.stringify({ message: "hi" }) }),
      ["chat", "stream"],
      { fetch: fetchImpl as unknown as typeof fetch, sleep: noSleep },
    );
    expect(res.headers.get("content-type")).toBe("text/event-stream");
    expect(res.headers.get("cache-control")).toMatch(/no-store/);
    expect(await res.text()).toContain("event: token");
  });

  test("backend asleep: a GET wakes it and retries once; a POST is not resent", async () => {
    let up = false;
    const fetchImpl = spy((url) => {
      if (url.endsWith("/health")) {
        up = true;
        return new Response("{}");
      }
      if (!up) throw new TypeError("connect ECONNREFUSED");
      return Response.json([]);
    });
    const deps = { fetch: fetchImpl as unknown as typeof fetch, sleep: noSleep };
    const get = await passthrough(req("/api/documents", { method: "GET", cookies: valid() }), ["documents"], deps);
    expect(get.status).toBe(200);

    up = false;
    fetchImpl.mockClear();
    const post = await passthrough(
      req("/api/search", { cookies: valid(), body: JSON.stringify({ q: "x" }) }),
      ["search"],
      deps,
    );
    expect(post.status).toBe(503);
    expect(await post.json()).toEqual({ code: "service_waking" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  test("exp only decides whether to refresh: a future exp is NOT authorization, upstream still decides", async () => {
    // Forged-looking token with a far-future exp: the BFF forwards it and trusts only FastAPI's answer.
    const forged = { [ACCESS_COOKIE]: fakeJwt(inMinutes(60 * 24 * 365), "forged") };
    const fetchImpl = spy(() => Response.json({ detail: "Not authenticated" }, { status: 401 }));
    const res = await passthrough(req("/api/documents", { method: "GET", cookies: forged }), ["documents"], {
      fetch: fetchImpl as unknown as typeof fetch,
      sleep: noSleep,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1); // exp did not short-circuit to "allowed"
    expect(res.status).toBe(401);
  });

  test("clock-skew margin: a token within 5 s of exp is refreshed first; 30 s left is still sent", async () => {
    const fetchImpl = spy(() => Response.json([]));
    const deps = { fetch: fetchImpl as unknown as typeof fetch, sleep: noSleep };
    const now = Math.floor(Date.now() / 1000);
    const near = await passthrough(req("/api/documents", { method: "GET", cookies: { [ACCESS_COOKIE]: fakeJwt(now + 3) } }), ["documents"], deps);
    expect(near.status).toBe(401);
    expect(fetchImpl).not.toHaveBeenCalled();
    await passthrough(req("/api/documents", { method: "GET", cookies: { [ACCESS_COOKIE]: fakeJwt(now + 30) } }), ["documents"], deps);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
