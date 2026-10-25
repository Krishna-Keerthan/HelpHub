import type { components } from "./schema";

export type ChatRequest = components["schemas"]["ChatRequest"];

/** One answer source. Shape documented in docs/api/chat-stream.md (not in the OpenAPI schema). */
export type ChatSource = {
  index: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  chunk_index: number;
  score: number;
};

/** The four SSE events of POST /chat/stream (docs/api/chat-stream.md). */
export type ChatEvent =
  | { event: "sources"; data: { conversation_id: string; sources: ChatSource[] } }
  | { event: "token"; data: { text: string } }
  | {
      event: "done";
      data: { conversation_id: string; status: "complete" | "no_answer"; cited: number[] };
    }
  | { event: "error"; data: { conversation_id?: string; code: string } };

const EVENT_NAMES = new Set(["sources", "token", "done", "error"]);

/** Parse one SSE message block ("event: x\ndata: {...}") into a ChatEvent, or null if unknown/invalid. */
export function parseSseMessage(block: string): ChatEvent | null {
  let event = "";
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  if (!EVENT_NAMES.has(event) || data.length === 0) return null;
  try {
    return { event, data: JSON.parse(data.join("\n")) } as ChatEvent;
  } catch {
    return null;
  }
}

/** Read an SSE response body and yield typed chat events as they arrive. */
export async function* readChatEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep: RegExpMatchArray | null;
      while ((sep = buffer.match(/\r?\n\r?\n/)) !== null) {
        const at = sep.index as number;
        const parsed = parseSseMessage(buffer.slice(0, at));
        buffer = buffer.slice(at + sep[0].length);
        if (parsed) yield parsed;
      }
    }
    const tail = parseSseMessage(buffer);
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}
