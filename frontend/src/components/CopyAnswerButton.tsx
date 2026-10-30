"use client";

import { useEffect, useRef, useState } from "react";
import { buttonClass, captionClass } from "./ui/styles";

const NOTE_MS = 2000;

/** Copies text to the clipboard. Renders nothing where the Clipboard API is unavailable. */
export function CopyAnswerButton({ text }: { text: string }) {
  const [note, setNote] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) return null;

  async function copy() {
    let message: string;
    try {
      await navigator.clipboard.writeText(text);
      message = "Copied";
    } catch {
      message = "Could not copy";
    }
    setNote(message);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setNote(null), NOTE_MS);
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
