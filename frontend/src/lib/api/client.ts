import createClient from "openapi-fetch";
import type { components, paths } from "./schema";
import { authedFetch } from "./authed-fetch";
import { readChatEvents, type ChatEvent, type ChatRequest } from "./sse";

export type { ChatEvent, ChatRequest, ChatSource } from "./sse";

/** Base path of the Next.js BFF; the browser never talks to FastAPI directly. */
export const API_BASE = "/api";

/** Typed JSON/multipart client for every route in docs/api/openapi.json. */
export const api = createClient<paths>({
  baseUrl: typeof location === "undefined" ? API_BASE : `${location.origin}${API_BASE}`,
  fetch: authedFetch,
});

export type LoginBody = components["schemas"]["LoginRequest"];

/** Log in through the BFF (sets httpOnly cookies). Returns the BFF error code on failure. */
export async function login(body: LoginBody): Promise<{ ok: true } | { ok: false; status: number; code: string; retryAfter: number | null }> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) return { ok: true };
  const code = ((await res.json().catch(() => ({}))) as { code?: string }).code ?? "login_failed";
  const retry = Number(res.headers.get("Retry-After"));
  return { ok: false, status: res.status, code, retryAfter: retry > 0 ? retry : null };
}

/** Log out through the BFF; local cookies are cleared even if the backend is down. */
export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, { method: "POST" });
}

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
  const res = await authedFetch(
    new Request(new URL(`${API_BASE}/chat/stream`, location.origin), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    }),
  );
  if (!res.ok || !res.body) {
    const retry = Number(res.headers.get("Retry-After"));
    throw new ChatHttpError(res.status, Number.isFinite(retry) && retry > 0 ? retry : null);
  }
  yield* readChatEvents(res.body);
}
