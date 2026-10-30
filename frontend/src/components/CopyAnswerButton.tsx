"use client";

import { useEffect, useRef, useState } from "react";
import { buttonClass, captionClass } from "./ui/styles";

const NOTE_MS = 2000;
/** Some embedded panes leave `writeText` pending forever; after this long the attempt counts as failed. */
export const COPY_TIMEOUT_MS = 3000;

/** Copies text to the clipboard. Renders nothing where the Clipboard API is unavailable. */
export function CopyAnswerButton({ text }: { text: string }) {
  const [note, setNote] = useState<string | null>(null);
  const noteTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const attempts = useRef(0);
  useEffect(
    () => () => {
      clearTimeout(noteTimer.current);
      attempts.current++; // an attempt still pending when the button goes away shows nothing
    },
    [],
  );
  if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) return null;

  async function copy() {
    const attempt = ++attempts.current;
    let settled = false;
    // Whichever of "copied", "failed" and "timed out" comes first decides the message; the others are ignored,
    // and so is anything from an older click once a newer one has started.
    const settle = (message: string) => {
      if (settled || attempts.current !== attempt) return;
      settled = true;
      setNote(message);
      clearTimeout(noteTimer.current);
      noteTimer.current = setTimeout(() => setNote(null), NOTE_MS);
    };
    const timeout = setTimeout(() => settle("Could not copy"), COPY_TIMEOUT_MS);
    try {
      await navigator.clipboard.writeText(text);
      settle("Copied");
    } catch {
      settle("Could not copy");
    } finally {
      clearTimeout(timeout);
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button type="button" onClick={() => void copy()} className={buttonClass({ variant: "ghost" })}>
        Copy
      </button>
      {/* The live region exists before its text does, so the note is announced. */}
      <span role="status" className={captionClass}>{note}</span>
    </span>
  );
}
