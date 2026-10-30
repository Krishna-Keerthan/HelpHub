"use client";

import { useEffect, useState } from "react";
import { REFUSAL_MESSAGE, streamErrorMessage, type Turn } from "@/lib/ui/chat-state";
import { displayCitations } from "@/lib/ui/citation-display";
import { AnswerMarkdown } from "./AnswerMarkdown";
import { CopyAnswerButton } from "./CopyAnswerButton";
import { Notice } from "./Notice";
import { SourceChips } from "./SourceChips";
import { captionClass } from "./ui/styles";

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
    <Notice className="mt-2">
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
        turn.answer && <AnswerMarkdown text={turn.answer} />
      )}
      {turn.status === "error" && (
        <p role="alert" className="mt-1 text-sm text-danger">
          {streamErrorMessage(turn.errorCode)}
        </p>
      )}
      {turn.status === "stopped" && <p className={`mt-1 ${captionClass}`}>Stopped.</p>}
      {turn.status === "streaming" && !turn.answer && turn.sources.length === 0 && <Searching />}
      {turn.status === "streaming" && !turn.answer && turn.sources.length > 0 && (
        <Notice className="mt-2">Found {turn.sources.length} matching {turn.sources.length === 1 ? "passage" : "passages"}. Writing the answer…</Notice>
      )}
      {turn.status === "streaming" && turn.answer && (
        <span aria-hidden="true" data-testid="streaming-indicator" className="inline-block motion-safe:animate-pulse">▍</span>
      )}
      <Citations turn={turn} />
    </>
  );
}

const LABEL = "text-xs font-semibold uppercase tracking-wide text-muted";

/** One exchange: the reader's question (right, tinted) and the assistant's answer (left, in a card). */
export function ChatMessage({ turn }: { turn: Turn }) {
  return (
    <li className="space-y-3 py-4 first:pt-0 last:pb-0">
      <div className="flex flex-col items-end gap-1">
        <p className={LABEL}>You</p>
        <p className="max-w-[90%] break-words rounded-lg bg-chip px-3 py-2 text-fg">{turn.question}</p>
      </div>
      <div className="flex flex-col items-start gap-1">
        <p className={LABEL}>HelpHub</p>
        <div className="w-full rounded-lg border border-line bg-surface-raised px-4 py-3">
          <div className="text-fg" aria-live="polite" aria-busy={turn.status === "streaming"}>
            <Answer turn={turn} />
          </div>
          {turn.status === "complete" && turn.answer && (
            <div className="mt-2 flex justify-end">
              <CopyAnswerButton text={displayCitations(turn.answer)} />
            </div>
          )}
        </div>
      </div>
    </li>
  );
}
