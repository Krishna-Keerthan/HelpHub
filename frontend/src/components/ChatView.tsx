"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ChatHttpError, streamChat } from "@/lib/api/client";
import { applyEvent, newTurn, REFUSAL_MESSAGE, streamErrorMessage, type Turn } from "@/lib/ui/chat-state";
import { failureMessage } from "@/lib/ui/failure";

const MAX_MESSAGE_CHARS = 2000;

function Citations({ turn }: { turn: Turn }) {
  const cited = turn.sources.filter((s) => turn.cited.includes(s.index));
  if (cited.length === 0) return null;
  return (
    <ul aria-label="Sources" className="mt-2 flex flex-wrap gap-2">
      {cited.map((s) => (
        <li
          key={s.chunk_id}
          title={`Document ${s.document_id}, section ${s.chunk_index}`}
          className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs"
        >
          [{s.index}] {s.document_title}
        </li>
      ))}
    </ul>
  );
}

function Answer({ turn }: { turn: Turn }) {
  if (turn.errorText) {
    return (
      <p role="alert" className="text-sm text-red-700">
        {turn.errorText}
      </p>
    );
  }
  return (
    <>
      {turn.status === "no_answer" ? (
        <p>{REFUSAL_MESSAGE}</p>
      ) : (
        <p className="whitespace-pre-wrap">{turn.answer}</p>
      )}
      {turn.status === "error" && (
        <p role="alert" className="mt-1 text-sm text-red-700">
          {streamErrorMessage(turn.errorCode)}
        </p>
      )}
      {turn.status === "streaming" && !turn.answer && <p className="text-sm text-zinc-500">Searching…</p>}
      <Citations turn={turn} />
    </>
  );
}

export function ChatView() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const conversationId = useRef<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const nextId = useRef(1);

  useEffect(() => () => abort.current?.abort(), []);

  const update = (id: number, fn: (t: Turn) => Turn) =>
    setTurns((cur) => cur.map((t) => (t.id === id ? fn(t) : t)));

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const message = String(new FormData(form).get("message") ?? "").trim();
    if (!message || busy) return;
    form.reset();
    const id = nextId.current++;
    setTurns((cur) => [...cur, newTurn(id, message)]);
    setBusy(true);
    abort.current = new AbortController();
    try {
      for await (const ev of streamChat(
        { message, conversation_id: conversationId.current },
        abort.current.signal,
      )) {
        if ("conversation_id" in ev.data && ev.data.conversation_id) {
          conversationId.current = ev.data.conversation_id;
        }
        update(id, (t) => applyEvent(t, ev));
      }
      // A stream that ends without done/error was cut off.
      update(id, (t) =>
        t.status === "streaming" ? { ...t, status: "error", errorCode: "interrupted" } : t,
      );
    } catch (err) {
      if (abort.current?.signal.aborted) return;
      const text =
        err instanceof ChatHttpError
          ? failureMessage(err.status, err.status === 503 ? "service_waking" : null, err.retryAfter)
          : "Connection lost. Check your connection and try again.";
      update(id, (t) => ({ ...t, status: "error", errorText: text }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Chat</h1>
      <ol className="space-y-6">
        {turns.map((t) => (
          <li key={t.id}>
            <p className="font-medium">{t.question}</p>
            <div className="mt-1 text-zinc-800" aria-live="polite">
              <Answer turn={t} />
            </div>
          </li>
        ))}
      </ol>
      <form onSubmit={onSubmit} className="flex gap-2" aria-label="Ask a question">
        <input
          name="message"
          required
          maxLength={MAX_MESSAGE_CHARS}
          aria-label="Your question"
          placeholder="Ask about your documents"
          className="flex-1 rounded border border-zinc-300 px-3 py-2"
        />
        <button type="submit" disabled={busy} className="rounded bg-zinc-900 px-4 py-2 text-white disabled:opacity-50">
          {busy ? "Answering…" : "Ask"}
        </button>
      </form>
    </section>
  );
}
