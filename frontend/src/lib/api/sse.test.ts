import { describe, expect, test } from "vitest";
import { parseSseMessage, readChatEvents } from "./sse";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(c) {
      for (const ch of chunks) c.enqueue(enc.encode(ch));
      c.close();
    },
  });
}

async function collect(body: ReadableStream<Uint8Array>) {
  const out = [];
  for await (const e of readChatEvents(body)) out.push(e);
  return out;
}

describe("parseSseMessage", () => {
  test("parses a token event", () => {
    expect(parseSseMessage('event: token\ndata: {"text":"hi"}')).toEqual({
      event: "token",
      data: { text: "hi" },
    });
  });
  test("ignores comments, unknown events and bad JSON", () => {
    expect(parseSseMessage(": waking")).toBeNull();
    expect(parseSseMessage('event: nope\ndata: {"a":1}')).toBeNull();
    expect(parseSseMessage("event: token\ndata: {oops")).toBeNull();
  });
});

describe("readChatEvents", () => {
  test("reassembles events split across chunks, including inside a multi-byte char", async () => {
    const full =
      'event: sources\ndata: {"conversation_id":"c","sources":[]}\n\n' +
      'event: token\ndata: {"text":"héllo"}\n\n' +
      'event: done\ndata: {"conversation_id":"c","status":"complete","cited":[]}\n\n';
    const bytes = new TextEncoder().encode(full);
    const cut = full.indexOf("é");
    const at = new TextEncoder().encode(full.slice(0, cut)).length + 1; // middle of "é"
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(bytes.slice(0, at));
        c.enqueue(bytes.slice(at));
        c.close();
      },
    });
    const events = await collect(body);
    expect(events.map((e) => e.event)).toEqual(["sources", "token", "done"]);
    expect(events[1]).toEqual({ event: "token", data: { text: "héllo" } });
  });

  test("yields an error event and handles CRLF separators", async () => {
    const events = await collect(
      streamOf(['event: error\r\ndata: {"conversation_id":"c","code":"embedding_unavailable"}\r\n\r\n']),
    );
    expect(events).toEqual([
      { event: "error", data: { conversation_id: "c", code: "embedding_unavailable" } },
    ]);
  });
});
