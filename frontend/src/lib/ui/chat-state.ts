import type { ChatEvent, ChatSource } from "@/lib/api/sse";
import { parseCitations } from "./citations";

export type Turn = {
  id: number;
  question: string;
  answer: string;
  sources: ChatSource[];
  cited: number[];
  /** "stopped" is client-side only: the reader pressed Stop. The server never sends it and a restore never produces it. */
  status: "streaming" | "complete" | "no_answer" | "error" | "stopped";
  /** Backend error code (in-stream) or a client label for HTTP failures. */
  errorCode?: string;
  /** Plain-language failure text for HTTP failures (429, waking, ...). */
  errorText?: string;
};

export function newTurn(id: number, question: string): Turn {
  return { id, question, answer: "", sources: [], cited: [], status: "streaming" };
}

/** Pure reducer: fold one SSE event into a turn. */
export function applyEvent(t: Turn, e: ChatEvent): Turn {
  switch (e.event) {
    case "sources":
      return { ...t, sources: e.data.sources };
    case "token":
      return { ...t, answer: t.answer + e.data.text };
    case "done":
      return { ...t, status: e.data.status, cited: e.data.cited };
    case "error":
      return { ...t, status: "error", errorCode: e.data.code };
  }
}

const IN_STREAM_ERRORS: Record<string, string> = {
  embedding_unavailable: "The search service is unavailable. Please try again later.",
  llm_rate_limited: "The assistant is busy right now. Please try again shortly.",
  llm_timeout: "The assistant took too long to answer. Please try again.",
  llm_unavailable: "The assistant is unavailable right now. Please try again later.",
  llm_model_unavailable: "The assistant is unavailable right now. Please try again later.",
  llm_bad_request: "The assistant could not handle that question. Try rephrasing it.",
  llm_empty_response: "The assistant did not produce an answer. Try rephrasing your question.",
};

/**
 * Client-side state, not a backend error.code: the stream ended without a done or error event.
 * Kept out of IN_STREAM_ERRORS, which maps only codes documented in docs/api/chat-stream.md.
 */
export const STREAM_CUT_OFF = "stream_cut_off";
export const STREAM_CUT_OFF_MESSAGE =
  "Something went wrong while answering: the connection dropped before the answer finished. Please ask again.";

export function streamErrorMessage(code: string | undefined): string {
  if (code === STREAM_CUT_OFF) return STREAM_CUT_OFF_MESSAGE;
  return (code && IN_STREAM_ERRORS[code]) || "Something went wrong while answering. Please try again.";
}

export const CONNECTION_LOST_MESSAGE = "Could not reach the server. Check your connection and ask again.";
export const CONVERSATION_GONE_MESSAGE = "That conversation is no longer available. Ask your question again to start a new one.";

/** Plain-language text for a chat request refused before the stream started. Never shows backend text. */
export function chatHttpMessage(status: number, retryAfter: number | null): string {
  if (status === 429) {
    return retryAfter
      ? `You are asking quickly. Wait ${retryAfter} seconds and ask again.`
      : "You are asking quickly. Wait a moment and ask again.";
  }
  if (status === 503) return "The server is waking up. This can take about a minute; ask again shortly.";
  if (status === 404) return CONVERSATION_GONE_MESSAGE;
  if (status === 422) return "That question cannot be sent. Questions must be between 1 and 2000 characters.";
  if (status === 403) return "This request was blocked for safety. Reload the page and ask again.";
  if (status >= 500) return "Something went wrong on our side. Please ask again in a moment.";
  return "The question could not be sent. Please try again.";
}

/** Shown for done.status === "no_answer" (detected by status, never by the text). */
export const REFUSAL_MESSAGE = "I couldn't find anything in your documents that answers this question.";

/** One row of GET /conversations/{id}/messages, as far as the client relies on it. */
export type MessageRow = { role: string; content: string; status: string; sources: unknown };

function isSource(s: unknown): s is ChatSource {
  if (typeof s !== "object" || s === null) return false;
  const o = s as Record<string, unknown>;
  return (
    Number.isInteger(o.index) &&
    typeof o.chunk_id === "string" &&
    typeof o.document_id === "string" &&
    typeof o.document_title === "string" &&
    Number.isInteger(o.chunk_index) &&
    typeof o.score === "number"
  );
}

/**
 * Rebuild turns from stored messages: each user message is paired with the assistant message right after
 * it. The server does not store `cited`, so it is recomputed from the answer; sources keep their original
 * `index` (an invalid one is dropped, never renumbered) and the citation count is the stored list length,
 * as in the backend. A row with an unknown role is skipped; an unknown status shows as cut off.
 */
export function messagesToTurns(rows: readonly MessageRow[]): { turns: Turn[]; nextId: number } {
  const turns: Turn[] = [];
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i]!;
    if (row.role !== "user") continue;
    const id = turns.length + 1;
    const next = rows[i + 1];
    if (next?.role !== "assistant") {
      turns.push({ id, question: row.content, answer: "", sources: [], cited: [], status: "error", errorCode: STREAM_CUT_OFF });
      continue;
    }
    i++;
    const stored = Array.isArray(next.sources) ? (next.sources as unknown[]) : [];
    const sources = stored.filter(isSource);
    const base = { id, question: row.content, answer: next.content, sources, cited: [] as number[] };
    switch (next.status) {
      case "complete":
        turns.push({ ...base, status: "complete", cited: parseCitations(next.content, stored.length) });
        break;
      case "no_answer":
        turns.push({ ...base, status: "no_answer" });
        break;
      case "failed":
        turns.push({ ...base, status: "error" });
        break;
      case "interrupted":
        turns.push({ ...base, status: "error", errorCode: STREAM_CUT_OFF });
        break;
      default:
        turns.push({ ...base, answer: "", sources: [], status: "error", errorCode: STREAM_CUT_OFF });
    }
  }
  return { turns, nextId: turns.length + 1 };
}
