import { vi } from "vitest";

type Handler = (req: Request) => Response | Promise<Response>;

/** Stub global fetch with handlers keyed "METHOD /path"; unknown routes fail the test loudly. */
export function routeFetch(routes: Record<string, Handler>) {
  const calls: { key: string; req: Request }[] = [];
  const impl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = input instanceof Request ? input : new Request(String(input), init);
    const key = `${req.method} ${new URL(req.url).pathname}`;
    calls.push({ key, req });
    const h = routes[key];
    if (!h) throw new Error(`unmocked request: ${key}`);
    return h(req);
  });
  vi.stubGlobal("fetch", impl);
  return { calls, keys: () => calls.map((c) => c.key) };
}

export const sse = (...events: [string, object][]) =>
  new Response(events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join(""), {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
