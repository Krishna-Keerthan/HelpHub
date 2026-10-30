"use client";

import { type FormEvent, type KeyboardEvent, type Ref } from "react";
import { buttonClass, inputClass } from "./ui/styles";

export const MAX_MESSAGE_CHARS = 2000;

type Props = {
  inputRef: Ref<HTMLTextAreaElement>;
  /** An answer is streaming: Ask is disabled and Stop is shown. */
  busy: boolean;
  /** The history is loading: nothing can be typed or sent. */
  restoring: boolean;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onStop: () => void;
};

/**
 * The question box, pinned to the bottom of the screen. Enter sends, Shift+Enter inserts a newline (and Enter
 * while an input method is composing text does neither). Typing stays possible while an answer streams;
 * sending waits for it, or Stop ends it.
 */
export function ChatComposer({ inputRef, busy, restoring, onSubmit, onStop }: Props) {
  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing) return;
    e.preventDefault();
    if (!busy) e.currentTarget.form?.requestSubmit();
  }
  return (
    <form
      onSubmit={onSubmit}
      aria-label="Ask a question"
      className="sticky bottom-0 z-10 -mx-4 flex items-end gap-2 border-t border-line bg-surface px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
    >
      <textarea
        ref={inputRef}
        name="message"
        required
        rows={2}
        maxLength={MAX_MESSAGE_CHARS}
        disabled={restoring}
        onKeyDown={onKeyDown}
        aria-label="Your question"
        placeholder="Ask about your documents"
        className={`max-h-40 min-w-0 flex-1 resize-none ${inputClass}`}
      />
      {busy && (
        <button type="button" onClick={onStop} className={buttonClass({ variant: "secondary" })}>
          Stop
        </button>
      )}
      <button type="submit" disabled={busy || restoring} className={buttonClass({ variant: "primary" })}>
        {busy ? "Answering…" : "Ask"}
      </button>
    </form>
  );
}
