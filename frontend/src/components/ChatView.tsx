"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, useConversationMessages } from "@/lib/query/hooks";
import { useIsClient } from "@/lib/session/use-is-client";
import { clearStored, CONVERSATION_STORAGE, readStored, writeStored } from "@/lib/session/storage";
import { ChatHttpError, streamChat } from "@/lib/api/client";
import {
  applyEvent,
  CONNECTION_LOST_MESSAGE,
  chatHttpMessage,
  messagesToTurns,
  newTurn,
  REFUSAL_MESSAGE,
  STREAM_CUT_OFF,
  streamErrorMessage,
  type Turn,
} from "@/lib/ui/chat-state";
import { displayCitations } from "@/lib/ui/citation-display";
import { Notice } from "./Notice";
import { SourceChips } from "./SourceChips";
import { DEMO_QUERIES } from "@/lib/demo-queries";

const MAX_MESSAGE_CHARS = 2000;
/** No first event after this long: the backend is probably cold-starting. */
export const SLOW_FIRST_EVENT_MS = 8000;

/** Shown from sending until the first event; switches to the cold-start message when that takes long. */
function Searching() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), SLOW_FIRST_EVENT_MS);
    return () => clearTimeout(t);
  }, []);
  return (
    <Notice className="mt-1 rounded">
      {slow ? "Waking the server, this can take about a minute…" : "Searching your documents…"}
    </Notice>
  );
}

function Citations({ turn }: { turn: Turn }) {
  const cited = turn.sources.filter((s) => turn.cited.includes(s.index));
  if (cited.length === 0) return null;
  return <SourceChips sources={cited} />;
}

function Answer({ turn }: { turn: Turn }) {
  if (turn.errorText) {
    return (
      <p role="alert" className="text-sm text-danger">
        {turn.errorText}
      </p>
    );
  }
  return (
    <>
      {turn.status === "no_answer" ? (
        <p>{REFUSAL_MESSAGE}</p>
      ) : (
        <p className="whitespace-pre-wrap break-words">{displayCitations(turn.answer)}</p>
      )}
      {turn.status === "error" && (
        <p role="alert" className="mt-1 text-sm text-danger">
          {streamErrorMessage(turn.errorCode)}
        </p>
      )}
      {turn.status === "streaming" && !turn.answer && turn.sources.length === 0 && <Searching />}
      {turn.status === "streaming" && !turn.answer && turn.sources.length > 0 && (
        <Notice className="mt-1 rounded">Found {turn.sources.length} matching {turn.sources.length === 1 ? "passage" : "passages"}. Writing the answer…</Notice>
      )}
      {turn.status === "streaming" && turn.answer && (
        <span aria-hidden="true" data-testid="streaming-indicator" className="inline-block motion-safe:animate-pulse">▍</span>
      )}
      <Citations turn={turn} />
    </>
  );
}

/** The restore reads sessionStorage, so the real view mounts only on the client (no hydration mismatch). */
export function ChatView() {
  return useIsClient() ? (
    <ChatSession />
  ) : (
    <section className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Chat</h1>
    </section>
  );
}

function ChatSession() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  // A stored conversation id (kept across a page change or refresh) is read once; its history is fetched
  // and hydrated into the turns once, after which local state is authoritative as before.
  const [restoreId] = useState(() => readStored(CONVERSATION_STORAGE));
  const conversationId = useRef<string | null>(restoreId);
  const abort = useRef<AbortController | null>(null);
  const [nextId, setNextId] = useState(1);
  const input = useRef<HTMLInputElement>(null);
  const [hydrated, setHydrated] = useState(false);
  const [alertDismissed, setAlertDismissed] = useState(false);
  const history = useConversationMessages(restoreId);
  const gone = history.error instanceof ApiError && history.error.status === 404;
  const restoring = restoreId !== null && !hydrated && !history.isError;

  if (restoreId !== null && !hydrated && history.data && !history.isFetching && !history.isError) {
    const restored = messagesToTurns(history.data);
    setHydrated(true);
    setTurns(restored.turns);
    setNextId(restored.nextId);
  }

  useEffect(() => () => abort.current?.abort(), []);

  // The conversation is gone (or not ours): forget it, the next question starts a new one.
  useEffect(() => {
    if (!gone) return;
    conversationId.current = null;
    clearStored(CONVERSATION_STORAGE);
  }, [gone]);

  const update = (id: number, fn: (t: Turn) => Turn) =>
    setTurns((cur) => cur.map((t) => (t.id === id ? fn(t) : t)));

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const message = String(new FormData(form).get("message") ?? "").trim();
    if (!message || busy || restoring) return;
    // Keep focus only if it was already in the form; never pull it from elsewhere.
    const focusWasInForm = form.contains(document.activeElement);
    form.reset();
    void send(message, focusWasInForm);
  }

  async function send(message: string, focusWasInForm: boolean) {
    const id = nextId;
    setNextId(id + 1);
    setAlertDismissed(true); // a failed history read no longer applies once a question has been sent
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
          writeStored(CONVERSATION_STORAGE, ev.data.conversation_id);
        }
        update(id, (t) => applyEvent(t, ev));
      }
      // A stream that ends without done/error was cut off.
      update(id, (t) =>
        t.status === "streaming" ? { ...t, status: "error", errorCode: STREAM_CUT_OFF } : t,
      );
    } catch (err) {
      if (abort.current?.signal.aborted) return;
      if (err instanceof ChatHttpError && err.status === 404) {
        conversationId.current = null;
        clearStored(CONVERSATION_STORAGE);
      }
      const text = err instanceof ChatHttpError ? chatHttpMessage(err.status, err.retryAfter) : CONNECTION_LOST_MESSAGE;
      update(id, (t) => ({ ...t, status: "error", errorText: text }));
    } finally {
      setBusy(false);
      const a = document.activeElement;
      if (focusWasInForm && (a === document.body || a === null)) {
        // The submit button was disabled while answering and dropped focus; give it back.
        setTimeout(() => input.current?.focus(), 0);
      }
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Chat</h1>
      {restoring && <Notice className="rounded">Loading conversation…</Notice>}
      {history.isError && !gone && !alertDismissed && (
        <p role="alert" className="text-sm text-danger">
          {history.error instanceof ApiError
            ? chatHttpMessage(history.error.status, history.error.retryAfter)
            : CONNECTION_LOST_MESSAGE}
        </p>
      )}
      {turns.length === 0 && !restoring && (
        <div className="rounded border border-dashed border-line p-6">
          <p className="text-center text-muted">
            Ask a question about your documents. HelpHub searches them and answers with citations to the documents it used.
          </p>
          <p className="mt-4 text-sm font-medium">Try one of these:</p>
          <ul aria-label="Suggested questions" className="mt-2 flex flex-col gap-2">
            {DEMO_QUERIES.map((q) => (
              <li key={q}>
                <button
                  type="button"
                  disabled={busy || restoring}
                  onClick={() => void send(q, false)}
                  className="min-h-10 w-full rounded border border-control-border px-3 py-2 text-left text-sm disabled:opacity-50"
                >
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <ol aria-label="Conversation" className="space-y-6">
        {turns.map((t) => (
          <li key={t.id}>
            <p className="break-words font-medium">{t.question}</p>
            <div className="mt-1 text-fg" aria-live="polite" aria-busy={t.status === "streaming"}>
              <Answer turn={t} />
            </div>
          </li>
        ))}
      </ol>
      <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row" aria-label="Ask a question">
        <input
          ref={input}
          name="message"
          required
          maxLength={MAX_MESSAGE_CHARS}
          disabled={restoring}
          aria-label="Your question"
          placeholder="Ask about your documents"
          className="min-h-10 flex-1 rounded border border-control-border bg-surface px-3 py-2 text-fg"
        />
        <button type="submit" disabled={busy || restoring} className="min-h-10 rounded bg-accent px-4 py-2 text-accent-fg disabled:opacity-50">
          {busy ? "Answering…" : "Ask"}
        </button>
      </form>
    </section>
  );
}
