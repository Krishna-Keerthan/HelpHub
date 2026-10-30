"use client";

import { useId } from "react";
import { PAGE_SIZES, lastPage } from "@/lib/ui/paging";
import { buttonClass, captionClass, inputClass } from "./styles";

type Props = {
  page: number;
  size: number;
  /** Rows on this page. */
  count: number;
  /** Workspace total, or null when the server did not report one. */
  total: number | null;
  onPage: (page: number) => void;
  onSize: (size: number) => void;
};

/**
 * Previous/Next and a page-size select. With a total it says "Showing 26 to 50 of 53"; without one it says
 * "Page 2" and Next is enabled only when the page came back full (there may be more).
 */
export function Pagination({ page, size, count, total, onPage, onSize }: Props) {
  const selectId = useId();
  const from = (page - 1) * size + 1;
  const summary =
    total === null ? `Page ${page}` : count === 0 ? `No documents on page ${page} of ${lastPage(total, size)}` : `Showing ${from} to ${from + count - 1} of ${total}`;
  const hasNext = total === null ? count >= size : page * size < total;
  return (
    <nav aria-label="Pagination" className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2">
      <p role="status" className={`mr-auto ${captionClass}`}>{summary}</p>
      <label htmlFor={selectId} className={captionClass}>Per page</label>
      <select
        id={selectId}
        value={size}
        onChange={(e) => onSize(Number(e.target.value))}
        className={inputClass}
      >
        {PAGE_SIZES.map((n) => (
          <option key={n} value={n}>{n}</option>
        ))}
      </select>
      <button type="button" className={buttonClass({ variant: "secondary" })} disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <button type="button" className={buttonClass({ variant: "secondary" })} disabled={!hasNext} onClick={() => onPage(page + 1)}>
        Next
      </button>
    </nav>
  );
}
