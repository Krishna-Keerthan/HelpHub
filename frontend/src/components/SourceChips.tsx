"use client";

import { useId, useState } from "react";
import { useDocumentExists } from "@/lib/query/hooks";
import type { ChatSource } from "@/lib/api/sse";
import { cardClass, captionClass, chipClass } from "@/components/ui/styles";

/**
 * Chip titles come from the stream (`document_title`). Opening a chip asks the server whether the document
 * still exists (GET /documents/{id}); only a 404 says it is gone. A document missing from some page of the
 * list, or a failed lookup, claims nothing.
 */
export function SourceChips({ sources }: { sources: ChatSource[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const panelId = useId();
  const open = sources.find((s) => s.index === openIndex);

  return (
    <div className="mt-2">
      <ul aria-label="Sources" className="flex flex-wrap gap-2">
        {sources.map((s) => (
          <li key={s.chunk_id}>
            <button
              type="button"
              aria-expanded={openIndex === s.index}
              aria-controls={openIndex === s.index ? panelId : undefined}
              onClick={() => setOpenIndex((cur) => (cur === s.index ? null : s.index))}
              className={chipClass("sm")}
            >
              [{s.index}] {s.document_title}
            </button>
          </li>
        ))}
      </ul>
      {open && <SourcePanel id={panelId} source={open} />}
    </div>
  );
}

/** Mounted only while its chip is open, so the existence check is requested on opening and not before. */
function SourcePanel({ id, source }: { id: string; source: ChatSource }) {
  const lookup = useDocumentExists(source.document_id, { enabled: true });
  const gone = lookup.status === "success" && !lookup.data.exists;
  return (
    <div id={id} role="region" aria-label={`Source ${source.index}`} className={`mt-2 text-sm ${cardClass}`}>
      <p className="font-medium">{source.document_title}</p>
      {gone && <p className={`mt-1 ${captionClass}`}>This document is no longer in your library.</p>}
      <p className={`mt-2 ${captionClass}`}>
        The answer does not include the cited passage, so only the document is shown.
      </p>
    </div>
  );
}
