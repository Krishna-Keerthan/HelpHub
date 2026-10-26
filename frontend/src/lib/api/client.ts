import createClient from "openapi-fetch";
import type { components, paths } from "./schema";
import { authedFetch } from "./authed-fetch";
import { resetSessionCache } from "@/lib/query/client";
import { readChatEvents, type ChatEvent, type ChatRequest } from "./sse";

export type { ChatEvent, ChatRequest, ChatSource } from "./sse";

/** Base path of the Next.js BFF; the browser never talks to FastAPI directly. */
export const API_BASE = "/api";

/** Seconds from a Retry-After header, or null when it is absent, not a positive finite number. */
export function retryAfterSeconds(res: Response): number | null {
  const n = Number(res.headers.get("Retry-After"));
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Typed JSON/multipart client for every route in docs/api/openapi.json. */
const apiUrl = (path: string) =>
  `${typeof location === "undefined" ? "" : location.origin}${API_BASE}${path}`;

export const api = createClient<paths>({
  baseUrl: apiUrl(""),
  fetch: authedFetch,
});

export type LoginBody = components["schemas"]["LoginRequest"];

/** Log in through the BFF (sets httpOnly cookies). Returns the BFF error code on failure. */
export async function login(body: LoginBody): Promise<{ ok: true } | { ok: false; status: number; code: string; retryAfter: number | null }> {
  resetSessionCache();
  const res = await fetch(apiUrl("/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    resetSessionCache(); // nothing from an earlier session may outlive the login
    return { ok: true };
  }
  const code = ((await res.json().catch(() => ({}))) as { code?: string }).code ?? "login_failed";
  return { ok: false, status: res.status, code, retryAfter: retryAfterSeconds(res) };
}

/** Log in as the shared demo viewer. The credentials live on the server; nothing is sent from here. */
export async function demoLogin(): Promise<{ ok: true } | { ok: false; status: number; code: string; retryAfter: number | null }> {
  resetSessionCache();
  const res = await fetch(apiUrl("/auth/demo"), { method: "POST" });
  if (res.ok) {
    resetSessionCache();
    return { ok: true };
  }
  const code = ((await res.json().catch(() => ({}))) as { code?: string }).code ?? "login_failed";
  return { ok: false, status: res.status, code, retryAfter: retryAfterSeconds(res) };
}

/** Log out through the BFF; local cookies are cleared even if the backend is down. */
export async function logout(): Promise<void> {
  resetSessionCache();
  try {
    await fetch(apiUrl("/auth/logout"), { method: "POST" });
  } finally {
    resetSessionCache();
  }
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
    new Request(apiUrl("/chat/stream"), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    }),
  );
  if (!res.ok || !res.body) {
    throw new ChatHttpError(res.status, retryAfterSeconds(res));
  }
  yield* readChatEvents(res.body);
}
