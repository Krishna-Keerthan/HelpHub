import type { ChatEvent, ChatSource } from "@/lib/api/sse";

export type Turn = {
  id: number;
  question: string;
  answer: string;
  sources: ChatSource[];
  cited: number[];
  status: "streaming" | "complete" | "no_answer" | "error";
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

export function streamErrorMessage(code: string | undefined): string {
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
