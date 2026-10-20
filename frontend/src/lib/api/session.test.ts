import { beforeEach, describe, expect, test, vi } from "vitest";
import { refreshSession, refreshWithBackoff, resetSessionForTests, type SessionDeps } from "./session";

function deps(post: () => Promise<Response>, over: Partial<SessionDeps> = {}): SessionDeps {
  let stamp = 0;
  return {
    post,
    now: () => 1000,
    sleep: async () => {},
    withLock: (fn) => fn(),
    readStamp: () => stamp,
    writeStamp: (ms) => {
      stamp = ms;
    },
    ...over,
  };
}
const ok = () => Promise.resolve(new Response("{}", { status: 200 }));
const status = (s: number) => () => Promise.resolve(new Response("{}", { status: s }));

beforeEach(resetSessionForTests);

describe("single-flight", () => {
  test("many parallel callers cause exactly one refresh request", async () => {
    const post = vi.fn(ok);
    const d = deps(post);
    const results = await Promise.all(Array.from({ length: 8 }, () => refreshSession(0, d)));
    expect(results).toEqual(Array(8).fill("ok"));
    expect(post).toHaveBeenCalledTimes(1);
  });

  test("a request sent before another tab's refresh adopts it without refreshing", async () => {
    const post = vi.fn(ok);
    const d = deps(post, { readStamp: () => 5000 }); // another tab refreshed at t=5000
    expect(await refreshSession(4000, d)).toBe("ok");
    expect(post).not.toHaveBeenCalled();
  });

  test("a request sent after the last refresh does refresh", async () => {
    const post = vi.fn(ok);
    const d = deps(post, { readStamp: () => 5000 });
    expect(await refreshSession(6000, d)).toBe("ok");
    expect(post).toHaveBeenCalledTimes(1);
  });

  test("the lock serialises two tabs: the second adopts the first's result", async () => {
    // Two "tabs" share one lock and one stamp store, like one browser profile.
    let stamp = 0;
    let tail: Promise<unknown> = Promise.resolve();
    const withLock = <T,>(fn: () => Promise<T>): Promise<T> => {
      const run = tail.then(fn);
      tail = run.catch(() => {});
      return run;
    };
    const post = vi.fn(ok);
    const shared = { withLock, readStamp: () => stamp, writeStamp: (m: number) => (stamp = m), now: () => 2000 };
    const tabA = deps(post, shared);
    const tabB = deps(post, shared);
    const a = refreshSession(1000, tabA);
    resetSessionForTests(); // separate tab = separate module state
    const b = refreshSession(1000, tabB);
    expect(await Promise.all([a, b])).toEqual(["ok", "ok"]);
    expect(post).toHaveBeenCalledTimes(1);
  });
});

describe("outcomes", () => {
  test("401 from the refresh itself is the only way to 'expired'", async () => {
    expect(await refreshSession(0, deps(status(401)))).toBe("expired");
  });
  test("503, network error and 5xx never mean expired", async () => {
    expect(await refreshSession(0, deps(status(503)))).toBe("waking");
    resetSessionForTests();
    expect(await refreshSession(0, deps(() => Promise.reject(new TypeError("net"))))).toBe("waking");
    resetSessionForTests();
    expect(await refreshSession(0, deps(status(502)))).toBe("indeterminate");
  });
});

describe("service waking up (cold start)", () => {
  test("bounded retries with backoff, UI told it is waking, then succeeds", async () => {
    const answers = [503, 503, 200];
    const post = vi.fn(() => Promise.resolve(new Response("{}", { status: answers.shift() })));
    const sleep = vi.fn(async () => {});
    const onWaking = vi.fn();
    const outcome = await refreshWithBackoff(0, onWaking, deps(post, { sleep }));
    expect(outcome).toBe("ok");
    expect(post).toHaveBeenCalledTimes(3);
    expect(sleep).toHaveBeenCalledTimes(2);
    expect(onWaking).toHaveBeenCalledWith(true);
    expect(onWaking).toHaveBeenLastCalledWith(false);
  });

  test("gives up after the bound and still does not report 'expired'", async () => {
    const post = vi.fn(status(503));
    const outcome = await refreshWithBackoff(0, () => {}, deps(post));
    expect(outcome).toBe("waking");
    expect(post).toHaveBeenCalledTimes(3); // 1 + 2 retries
  });

  test("indeterminate is never retried automatically (token may already be rotated)", async () => {
    const post = vi.fn(status(502));
    expect(await refreshWithBackoff(0, () => {}, deps(post))).toBe("indeterminate");
    expect(post).toHaveBeenCalledTimes(1);
  });
});
