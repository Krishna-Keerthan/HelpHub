import createClient from "openapi-fetch";
import type { paths } from "./schema";
import { readChatEvents, type ChatEvent, type ChatRequest } from "./sse";

export type { ChatEvent, ChatRequest, ChatSource } from "./sse";

/** Base path of the Next.js BFF; the browser never talks to FastAPI directly. */
export const API_BASE = "/api";

/** Typed JSON/multipart client for every route in docs/api/openapi.json. */
export const api = createClient<paths>({ baseUrl: API_BASE });

/** Failure before the stream starts (plain HTTP error). */
export class ChatHttpError extends Error {
  constructor(
    readonly status: number,
    /** Seconds from the Retry-After header on 429, otherwise null. */
    readonly retryAfter: number | null,
  ) {
    super(`chat request failed with HTTP ${status}`);
  }
}

/** POST /chat/stream. Yields events; throws ChatHttpError for non-200 before the stream starts. */
export async function* streamChat(
  body: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const retry = Number(res.headers.get("Retry-After"));
    throw new ChatHttpError(res.status, Number.isFinite(retry) && retry > 0 ? retry : null);
  }
  yield* readChatEvents(res.body);
}
