"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { api } from "@/lib/api/client";
import type { ChatSource } from "@/lib/api/sse";

/** document id -> title, or "failed" when the list could not be loaded. */
type Titles = Map<string, string> | "failed" | null;

/** Resolves document titles from the documents list, fetched once on first use. */
export function useDocumentTitles(): { titles: Titles; ensure: () => void } {
  const [titles, setTitles] = useState<Titles>(null);
  const [started, setStarted] = useState(false);
  function ensure() {
    if (started) return;
    setStarted(true);
    void (async () => {
      try {
        const { data } = await api.GET("/documents");
        setTitles(data ? new Map(data.map((d) => [d.id, d.title])) : "failed");
      } catch {
        setTitles("failed");
      }
    })();
  }
  return { titles, ensure };
}

export function SourceChips({
  sources,
  titles,
  onOpen,
}: {
  sources: ChatSource[];
  titles: Titles;
  onOpen: () => void;
}) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const panelId = useId();
  const open = sources.find((s) => s.index === openIndex);
  const titleOf = (s: ChatSource) => (titles instanceof Map ? titles.get(s.document_id) : undefined) ?? s.document_title;
  const gone = (s: ChatSource) => titles instanceof Map && !titles.has(s.document_id);

  return (
    <div className="mt-2">
      <ul aria-label="Sources" className="flex flex-wrap gap-2">
        {sources.map((s) => (
          <li key={s.chunk_id}>
            <button
              type="button"
              aria-expanded={openIndex === s.index}
              aria-controls={openIndex === s.index ? panelId : undefined}
              onClick={() => {
                onOpen();
                setOpenIndex((cur) => (cur === s.index ? null : s.index));
              }}
              className="min-h-8 rounded-full bg-chip px-3 py-0.5 text-left text-xs"
            >
              [{s.index}] {titleOf(s)}
            </button>
          </li>
        ))}
      </ul>
      {open && (
        <div id={panelId} role="region" aria-label={`Source ${open.index}`} className="mt-2 rounded border border-line p-3 text-sm">
          <p className="font-medium">{titleOf(open)}</p>
          <p className="text-xs text-muted">Section {open.chunk_index + 1} of this document</p>
          {gone(open) && (
            <p className="mt-1 text-xs text-muted">This document is no longer in your library.</p>
          )}
          <p className="mt-2 text-xs text-muted">
            The answer does not include the cited passage, so only the document is shown.
          </p>
          {!gone(open) && (
            <Link href="/documents" className="mt-2 inline-block min-h-8 text-xs underline">
              Open the documents list
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
