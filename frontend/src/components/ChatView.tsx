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
  STREAM_CUT_OFF,
  type Turn,
} from "@/lib/ui/chat-state";
import { useStickToBottom } from "@/lib/ui/use-stick-to-bottom";
import { ChatComposer } from "./ChatComposer";
import { ChatMessages } from "./ChatMessages";
import { Notice } from "./Notice";
import { buttonClass, emptyClass, titleClass } from "./ui/styles";
import { DEMO_QUERIES } from "@/lib/demo-queries";

export { SLOW_FIRST_EVENT_MS } from "./ChatMessage";

/** The restore reads sessionStorage, so the real view mounts only on the client (no hydration mismatch). */
export function ChatView() {
  return useIsClient() ? (
    <ChatSession />
  ) : (
    <section className="flex flex-col gap-4">
      <h1 className={titleClass}>Chat</h1>
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
  const input = useRef<HTMLTextAreaElement>(null);
  // The turn being answered, so Stop can mark it.
  const activeId = useRef<number | null>(null);
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

  // Forget the current conversation: the next question starts a new one. The server's history is untouched.
  const forgetConversation = () => {
    conversationId.current = null;
    clearStored(CONVERSATION_STORAGE);
  };

  // The conversation is gone (or not ours): forget it.
  useEffect(() => {
    if (gone) forgetConversation();
  }, [gone]);

  // After a restore or a new message, keep the latest in view; while streaming, only if already near the bottom.
  const { endRef, follow } = useStickToBottom(turns, turns.length > 0);

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
    follow(); // their own question and the answer should be in view
    setBusy(true);
    const controller = new AbortController();
    abort.current = controller;
    activeId.current = id;
    try {
      for await (const ev of streamChat({ message, conversation_id: conversationId.current }, controller.signal)) {
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
      if (controller.signal.aborted) return; // Stop, New chat or leaving the page
      if (err instanceof ChatHttpError && err.status === 404) forgetConversation();
      const text = err instanceof ChatHttpError ? chatHttpMessage(err.status, err.retryAfter) : CONNECTION_LOST_MESSAGE;
      update(id, (t) => ({ ...t, status: "error", errorText: text }));
    } finally {
      // A newer question may already be streaming (New chat, then ask): only the latest request resets the state.
      if (abort.current !== controller) return;
      setBusy(false);
      const a = document.activeElement;
      if (focusWasInForm && (a === document.body || a === null)) {
        // The submit button was disabled while answering and dropped focus; give it back.
        setTimeout(() => input.current?.focus(), 0);
      }
    }
  }

  /** Stop: end the stream and keep what has arrived. */
  function onStop() {
    abort.current?.abort();
    const id = activeId.current;
    if (id !== null) update(id, (t) => (t.status === "streaming" ? { ...t, status: "stopped" } : t));
    setBusy(false);
    setTimeout(() => input.current?.focus(), 0);
  }

  /** New chat: end any answer in progress, forget the conversation and show the empty state again. */
  function onNewChat() {
    abort.current?.abort();
    abort.current = null;
    activeId.current = null;
    forgetConversation();
    setTurns([]);
    setNextId(1);
    setBusy(false);
    setAlertDismissed(true);
    setTimeout(() => input.current?.focus(), 0);
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className={titleClass}>Chat</h1>
        {turns.length > 0 && !restoring && (
          <button type="button" onClick={onNewChat} className={buttonClass({ variant: "secondary" })}>
            New chat
          </button>
        )}
      </div>
      {restoring && <Notice>Loading conversation…</Notice>}
      {history.isError && !gone && !alertDismissed && (
        <p role="alert" className="text-sm text-danger">
          {history.error instanceof ApiError
            ? chatHttpMessage(history.error.status, history.error.retryAfter)
            : CONNECTION_LOST_MESSAGE}
        </p>
      )}
      {turns.length === 0 && !restoring && (
        <div className={emptyClass}>
          <p className="text-center text-muted">
            Ask a question about your documents. HelpHub searches them and answers with citations to the documents it used.
          </p>
          <p className="mt-6 text-sm font-medium">Try one of these:</p>
          <ul aria-label="Suggested questions" className="mt-2 grid gap-2 sm:grid-cols-2">
            {DEMO_QUERIES.map((q) => (
              <li key={q}>
                <button
                  type="button"
                  disabled={busy || restoring}
                  onClick={() => void send(q, false)}
                  className={`${buttonClass({ variant: "secondary", block: true })} h-full justify-start py-2 text-left`}
                >
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <ChatMessages turns={turns} />
      {/* scroll-mb: the sticky composer (about 6rem) covers the bottom of the screen, so stop above it. */}
      <div ref={endRef} aria-hidden="true" className="scroll-mb-32" />
      <ChatComposer inputRef={input} busy={busy} restoring={restoring} onSubmit={onSubmit} onStop={onStop} />
    </section>
  );
}
