"use client";

import { useEffect, useRef, useState } from "react";
import { api, retryAfterSeconds } from "@/lib/api/client";
import { DEMO_QUERIES } from "@/lib/demo-queries";
import { failureMessage } from "@/lib/ui/failure";
import {
  COLUMN_CAPTIONS,
  HYBRID_NOTE,
  KEYWORD_NOTE,
  MODES,
  RANK_HELP,
  REVEAL_STEP_MS,
  SIMILARITY_HELP,
  showsSimilarity,
  snippet,
  uniqueDocumentIds,
  whyListed,
  type SearchHit,
  type SearchMode,
} from "@/lib/ui/compare";
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
    return { state: "error", message: failureMessage(response.status, null, retryAfterSeconds(response)) };
  } catch (e) {
    console.error("search failed:", e instanceof Error ? e.constructor.name : typeof e);
    return { state: "error", message: "Could not reach the service. Check your connection and try again." };
  }
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;

export function CompareView() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [columns, setColumns] = useState<Columns>({});
  const latest = useRef(0);
  // Columns are fetched in parallel; this only paces when finished ones appear (presentation).
  const [stage, setStage] = useState(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  useEffect(() => clearTimers, []);

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
    clearTimers();
    if (prefersReducedMotion()) {
      setStage(MODES.length);
    } else {
      setStage(1);
      for (let n = 2; n <= MODES.length; n++) {
        timers.current.push(setTimeout(() => setStage(n), (n - 1) * REVEAL_STEP_MS));
      }
    }
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

  // Errors show at once. A finished column appears when its turn has come and the column before it is
  // showing, so the order is always Vector, Keyword, Hybrid.
  const visible: boolean[] = [];
  MODES.forEach(({ mode }, i) => {
    const col = columns[mode];
    visible[i] =
      col?.state === "error" || (col?.state === "done" && stage > i && (i === 0 || visible[i - 1] === true));
  });

  return (
    <section data-wide>
      <h1 className="mb-4 text-xl font-semibold">Compare retrieval</h1>
      <p className="mb-4 max-w-prose text-sm text-muted">
        Each column shows the passages (pieces of your documents) that one retrieval mode returns for the same question.
        Vector compares meaning: it returns the passages closest to the question. Keyword matches the words and codes
        in the question against the passage text. Hybrid merges the vector and keyword rankings into one list.
      </p>
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
          {MODES.map(({ mode, label }, i) => {
            const col = visible[i] ? columns[mode] : undefined;
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
                  <>
                  <p className="mb-2 text-xs text-muted">{COLUMN_CAPTIONS[mode]}</p>
                  {mode === "keyword" && <p className="mb-2 text-xs text-muted">{KEYWORD_NOTE}</p>}
                  {mode === "hybrid" && <p className="mb-2 text-xs text-muted">{HYBRID_NOTE}</p>}
                  <ol aria-label={`${label} results`} className="space-y-3">
                    {col.hits.map((h, n) => (
                      <li key={h.chunk_id} className="rounded border border-line p-3 text-sm">
                        <p className="text-xs font-medium" title={RANK_HELP}>
                          {whyListed(h, mode)}
                        </p>
                        <div className="mt-1 flex flex-wrap items-baseline gap-x-2">
                          <span className="text-muted">#{n + 1}</span>
                          <span className="min-w-0 break-words font-medium">{h.document_title}</span>
                        </div>
                        {showsSimilarity(mode) && h.score !== null && (
                          <p className="text-xs text-muted" title={SIMILARITY_HELP}>
                            Similarity {h.score.toFixed(3)}
                            <span className="sr-only"> ({SIMILARITY_HELP})</span>
                          </p>
                        )}
                        {unique.get(mode)?.has(h.document_id) && (
                          <p className="mt-1 inline-block rounded bg-info px-2 py-0.5 text-xs text-info-fg">
                            Only in this list
                          </p>
                        )}
                        <p className="mt-1 break-words">{snippet(h.content)}</p>
                      </li>
                    ))}
                  </ol>
                  </>
                )}
              </section>
            );
          })}
        </div>
      )}
    </section>
  );
}
