import { afterEach, expect, test, vi } from "vitest";
import { ChatHttpError, streamChat } from "./client";

afterEach(() => vi.unstubAllGlobals());

test("streamChat maps a 429 to ChatHttpError with Retry-After seconds", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("{}", { status: 429, headers: { "Retry-After": "7" } })),
  );
  const run = async () => {
    for await (const _ of streamChat({ message: "hi" })) void _;
  };
  await expect(run()).rejects.toMatchObject({ status: 429, retryAfter: 7 });
  await expect(run()).rejects.toBeInstanceOf(ChatHttpError);
});

test("streamChat yields events from a 200 stream", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response('event: token\ndata: {"text":"a"}\n\n', {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    ),
  );
  const got = [];
  for await (const e of streamChat({ message: "hi" })) got.push(e);
  expect(got).toEqual([{ event: "token", data: { text: "a" } }]);
});
