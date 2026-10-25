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
  embedding_unavailable: "Search is temporarily unavailable. Please try again in a moment.",
  llm_rate_limited: "The assistant is busy right now. Please try again shortly.",
  llm_timeout: "The assistant took too long to answer. Please try again.",
  llm_unavailable: "The assistant is unavailable right now. Please try again later.",
  llm_empty_response: "The assistant did not produce an answer. Try rephrasing your question.",
};

export function streamErrorMessage(code: string | undefined): string {
  return (code && IN_STREAM_ERRORS[code]) || "Something went wrong while answering. Please try again.";
}

/** Shown for done.status === "no_answer" (detected by status, never by the text). */
export const REFUSAL_MESSAGE = "I couldn't find anything in your documents that answers this question.";
