"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api/client";
import { DEMO_QUERIES } from "@/lib/demo-queries";
import { failureMessage } from "@/lib/ui/failure";
import { MODES, snippet, uniqueDocumentIds, type SearchHit, type SearchMode } from "@/lib/ui/compare";
import { Notice } from "./Notice";

const RESULTS_PER_MODE = 5; // same as the backend default; the generated type requires it

type Column =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "done"; hits: SearchHit[] };

type Columns = Partial<Record<SearchMode, Column>>;

async function runSearch(mode: SearchMode, query: string): Promise<Column> {
  try {
    const { data, response } = await api.POST("/search", { body: { query, mode, k: RESULTS_PER_MODE } });
    if (data) return { state: "done", hits: data };
    const retry = Number(response.headers.get("Retry-After"));
    return { state: "error", message: failureMessage(response.status, null, retry > 0 ? retry : null) };
  } catch {
    return { state: "error", message: "Could not reach the service. Check your connection and try again." };
  }
}

export function CompareView() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [columns, setColumns] = useState<Columns>({});
  const latest = useRef(0);

  function runModes(q: string, modes: readonly SearchMode[]) {
    const run = ++latest.current;
    setColumns((cur) => ({ ...cur, ...Object.fromEntries(modes.map((m) => [m, { state: "loading" } as Column])) }));
    for (const mode of modes) {
      void runSearch(mode, q).then((col) => {
        if (run === latest.current) setColumns((cur) => ({ ...cur, [mode]: col }));
      });
    }
  }

  function submit(raw: string) {
    const q = raw.trim();
    if (!q) return;
    setQuery(q);
    setSubmitted(q);
    setColumns({});
    runModes(q, MODES.map((m) => m.mode));
  }

  const loadedHits: Partial<Record<SearchMode, SearchHit[]>> = {};
  for (const { mode } of MODES) {
    const col = columns[mode];
    if (col?.state === "done") loadedHits[mode] = col.hits;
  }
  // Overlap is only meaningful when every column loaded; with one missing or pending, a "unique"
  // document might simply be in the list we do not have yet.
  const allLoaded = MODES.every(({ mode }) => loadedHits[mode] !== undefined);
  const unique = allLoaded ? uniqueDocumentIds(loadedHits) : new Map<SearchMode, Set<string>>();

  return (
    <section data-wide>
      <h1 className="mb-4 text-xl font-semibold">Compare retrieval</h1>
      <form
        className="mb-2 flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit(query);
        }}
      >
        <label htmlFor="compare-query" className="sr-only">
          Search query
        </label>
        <input
          id="compare-query"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="min-h-10 min-w-0 flex-1 basis-60 rounded border border-control-border bg-surface px-3"
        />
        <button type="submit" className="min-h-10 rounded bg-accent px-4 text-sm text-accent-fg">
          Compare
        </button>
      </form>
      <ul aria-label="Suggested queries" className="mb-4 flex flex-wrap gap-2">
        {DEMO_QUERIES.map((q) => (
          <li key={q}>
            <button type="button" className="min-h-10 rounded-full bg-chip px-3 text-sm" onClick={() => submit(q)}>
              {q}
            </button>
          </li>
        ))}
      </ul>
      {submitted === null ? (
        <p className="text-sm text-muted">Enter a question to see what each retrieval mode returns.</p>
      ) : (
        <div className="grid gap-6 sm:grid-cols-3">
          {MODES.map(({ mode, label }) => {
            const col = columns[mode];
            const headingId = `compare-${mode}`;
            return (
              <section key={mode} aria-labelledby={headingId} className="min-w-0">
                <h2 id={headingId} className="mb-2 font-semibold">
                  {label}
                </h2>
                {!col || col.state === "loading" ? (
                  <Notice className="rounded">Searching…</Notice>
                ) : col.state === "error" ? (
                  <div>
                    <p role="alert" className="mb-2 text-sm text-danger">
                      {col.message}
                    </p>
                    <button
                      type="button"
                      aria-label={`Retry ${label}`}
                      className="min-h-10 rounded border border-control-border px-3 text-sm"
                      onClick={() => runModes(submitted, [mode])}
                    >
                      Try again
                    </button>
                  </div>
                ) : col.hits.length === 0 ? (
                  <p className="rounded border border-dashed border-line p-4 text-sm text-muted">No results.</p>
                ) : (
                  <ol aria-label={`${label} results`} className="space-y-3">
                    {col.hits.map((h, i) => (
                      <li key={h.chunk_id} className="rounded border border-line p-3 text-sm">
                        <div className="flex flex-wrap items-baseline gap-x-2">
                          <span className="text-muted">#{i + 1}</span>
                          <span className="min-w-0 break-words font-medium">{h.document_title}</span>
                        </div>
                        {h.score !== null && <p className="text-xs text-muted">Score {h.score.toFixed(3)}</p>}
                        {unique.get(mode)?.has(h.document_id) && (
                          <p className="mt-1 inline-block rounded bg-info px-2 py-0.5 text-xs text-info-fg">
                            Only in this list
                          </p>
                        )}
                        <p className="mt-1 break-words">{snippet(h.content)}</p>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            );
          })}
        </div>
      )}
    </section>
  );
}
