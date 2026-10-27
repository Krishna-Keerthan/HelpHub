"use client";

import { useId, useState } from "react";
import { useDocuments } from "@/lib/query/hooks";
import type { ChatSource } from "@/lib/api/sse";
import { cardClass, captionClass, chipClass } from "@/components/ui/styles";

/**
 * Titles come from the shared documents query. It is not requested until a chip is used, but a list
 * already cached (for example from the Documents page) is used straight away.
 */
export function SourceChips({ sources }: { sources: ChatSource[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [used, setUsed] = useState(false);
  const documents = useDocuments({ enabled: used });
  const titles = documents.data ? new Map(documents.data.map((d) => [d.id, d.title])) : null;
  const panelId = useId();
  const open = sources.find((s) => s.index === openIndex);
  const titleOf = (s: ChatSource) => (titles?.get(s.document_id)) ?? s.document_title;
  const gone = (s: ChatSource) => titles !== null && !titles.has(s.document_id);

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
                setUsed(true);
                setOpenIndex((cur) => (cur === s.index ? null : s.index));
              }}
              className={chipClass("sm")}
            >
              [{s.index}] {titleOf(s)}
            </button>
          </li>
        ))}
      </ul>
      {open && (
        <div id={panelId} role="region" aria-label={`Source ${open.index}`} className={`mt-2 text-sm ${cardClass}`}>
          <p className="font-medium">{titleOf(open)}</p>
          {gone(open) && (
            <p className={`mt-1 ${captionClass}`}>This document is no longer in your library.</p>
          )}
          <p className={`mt-2 ${captionClass}`}>
            The answer does not include the cited passage, so only the document is shown.
          </p>
        </div>
      )}
    </div>
  );
}
