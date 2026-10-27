"use client";

import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, retryAfterSeconds } from "@/lib/api/client";
import { DEMO_QUERIES } from "@/lib/demo-queries";
import { failureMessage } from "@/lib/ui/failure";
import {
  canRevealNext,
  columnCaption,
  compareIntro,
  HYBRID_NOTE,
  MODES,
  RANK_HELP,
  RANK_ONLY_NOTE,
  REVEAL_STEP_MS,
  SIMILARITY_HELP,
  showsSimilarity,
  snippet,
  uniqueDocumentIds,
  whyListed,
  type ColumnStatus,
  type SearchHit,
  type SearchMode,
} from "@/lib/ui/compare";
import { COMPARE_KEY } from "@/lib/query/invalidate";
import { useIsClient } from "@/lib/session/use-is-client";
import { COMPARE_QUERY_STORAGE, readStored, writeStored } from "@/lib/session/storage";
import { Notice } from "./Notice";
import { buttonClass, cardClass, captionClass, chipClass, emptyClass, headingClass, inputClass, titleClass } from "./ui/styles";

const RESULTS_PER_MODE = 5; // same as the backend default; the generated type requires it
/** How long one mode's results for one query are reused from the in-memory cache (a choice, see D15). */
export const COMPARE_STALE_MS = 5 * 60_000;
const compareKey = (mode: SearchMode, query: string) => [...COMPARE_KEY, mode, query] as const;

class SearchFailed extends Error {
  constructor(readonly column: Column) {
    super("search failed");
  }
}

type Column =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "done"; hits: SearchHit[] };

type Columns = Partial<Record<SearchMode, Column>>;

async function fetchColumn(mode: SearchMode, query: string): Promise<SearchHit[]> {
  try {
    const { data, response } = await api.POST("/search", { body: { query, mode, k: RESULTS_PER_MODE } });
    if (data) return data;
    throw new SearchFailed({ state: "error", message: failureMessage(response.status, null, retryAfterSeconds(response)) });
  } catch (e) {
    if (e instanceof SearchFailed) throw e;
    console.error("search failed:", e instanceof Error ? e.constructor.name : typeof e);
    throw new SearchFailed({ state: "error", message: "Could not reach the service. Check your connection and try again." });
  }
}

/** Through the query cache; a failure throws, so an error is never cached and "Try again" really retries. */
async function runSearch(client: QueryClient, mode: SearchMode, query: string): Promise<Column> {
  try {
    const hits = await client.fetchQuery({
      queryKey: compareKey(mode, query),
      queryFn: () => fetchColumn(mode, query),
      staleTime: COMPARE_STALE_MS,
      retry: false,
    });
    return { state: "done", hits };
  } catch (e) {
    return e instanceof SearchFailed ? e.column : { state: "error", message: "Could not reach the service. Check your connection and try again." };
  }
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;

/** The restore reads sessionStorage, so the real view mounts only on the client (no hydration mismatch). */
export function CompareView() {
  return useIsClient() ? (
    <CompareSession />
  ) : (
    <section data-wide>
      <h1 className={`mb-4 ${titleClass}`}>Compare retrieval</h1>
    </section>
  );
}

function CompareSession() {
  const client = useQueryClient();
  // After a page change or refresh the last submitted query comes back from sessionStorage. Columns
  // already in the cache are shown at once (no request); the others load, with no step delay (reduced).
  const [restored] = useState(() => readStored(COMPARE_QUERY_STORAGE));
  const [query, setQuery] = useState(restored ?? "");
  const [submitted, setSubmitted] = useState<string | null>(restored);
  const [columns, setColumns] = useState<Columns>(() => {
    if (!restored) return {};
    return Object.fromEntries(
      MODES.map(({ mode }) => {
        const hits = client.getQueryData<SearchHit[]>(compareKey(mode, restored));
        return [mode, hits ? { state: "done", hits } : { state: "loading" }];
      }),
    ) as Columns;
  });
  const latest = useRef(0);
  // Columns are fetched in parallel; this only paces when finished ones appear (presentation). `cooledFor`
  // is the number of shown columns whose step has elapsed; `floor` keeps columns shown while one is retried.
  const [reduced, setReduced] = useState(restored !== null);
  const [cooledFor, setCooledFor] = useState(0);
  const [floor, setFloor] = useState(0);
  const [retried, setRetried] = useState<ReadonlySet<SearchMode>>(new Set());

  const statuses: ColumnStatus[] = MODES.map(({ mode }) => {
    const state = columns[mode]?.state;
    return state === "done" || state === "error" ? state : "pending";
  });
  let revealed = 0;
  while (canRevealNext(revealed, statuses, cooledFor >= revealed)) revealed++;
  revealed = Math.max(revealed, floor);

  useEffect(() => {
    if (reduced || revealed === 0 || revealed >= MODES.length) return;
    const timer = setTimeout(() => setCooledFor(revealed), REVEAL_STEP_MS);
    return () => clearTimeout(timer);
  }, [reduced, revealed]);

  const startSearches = useCallback(
    (q: string, modes: readonly SearchMode[]) => {
      const run = ++latest.current;
      for (const mode of modes) {
        void runSearch(client, mode, q).then((col) => {
          if (run === latest.current) setColumns((cur) => ({ ...cur, [mode]: col }));
        });
      }
    },
    [client],
  );

  function runModes(q: string, modes: readonly SearchMode[]) {
    setColumns((cur) => ({ ...cur, ...Object.fromEntries(modes.map((m) => [m, { state: "loading" } as Column])) }));
    startSearches(q, modes);
  }

  useEffect(() => {
    if (!restored) return;
    startSearches(
      restored,
      MODES.map((m) => m.mode).filter((m) => client.getQueryData(compareKey(m, restored)) === undefined),
    );
  }, [client, restored, startSearches]);

  function submit(raw: string) {
    const q = raw.trim();
    if (!q) return;
    writeStored(COMPARE_QUERY_STORAGE, q);
    setQuery(q);
    setSubmitted(q);
    setColumns({});
    setReduced(prefersReducedMotion());
    setCooledFor(0);
    setFloor(0);
    setRetried(new Set());
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

  // Errors show at once. A finished column appears once the ones before it have, so the order is always
  // Vector, Keyword, Hybrid; with reduced motion each appears as soon as it is done. A retried column
  // shows as soon as it is done.
  const visible = MODES.map(
    ({ mode }, i) => statuses[i] === "error" || (statuses[i] === "done" && (reduced || i < revealed || retried.has(mode))),
  );

  return (
    <section data-wide>
      <h1 className={`mb-4 ${titleClass}`}>Compare retrieval</h1>
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
          className={`min-w-0 flex-1 basis-60 ${inputClass}`}
        />
        <button type="submit" className={buttonClass({ variant: "primary" })}>
          Compare
        </button>
      </form>
      <ul aria-label="Suggested queries" className="mb-4 flex flex-wrap gap-2">
        {DEMO_QUERIES.map((q) => (
          <li key={q}>
            <button type="button" className={chipClass("md")} onClick={() => submit(q)}>
              {q}
            </button>
          </li>
        ))}
      </ul>
      {submitted === null ? (
        <p className="text-sm text-muted">Enter a question to see what each retrieval mode returns.</p>
      ) : (
        <>
        <p className={`mb-4 ${captionClass}`}>{compareIntro(submitted)}</p>
        {/* sm and up: each column spans three shared rows (heading, notes, results) so the first cards line up. */}
        <div className="grid gap-y-8 sm:grid-cols-3 sm:gap-x-6 sm:gap-y-0">
          {MODES.map(({ mode, label }, i) => {
            const col = visible[i] ? columns[mode] : undefined;
            const headingId = `compare-${mode}`;
            const hasHits = col !== undefined && col.state !== "loading" && col.state !== "error" && col.hits.length > 0;
            return (
              <section key={mode} aria-labelledby={headingId} className="min-w-0 sm:row-span-3 sm:grid sm:grid-rows-subgrid">
                <h2 id={headingId} className={`mb-2 ${headingClass}`}>
                  {label}
                </h2>
                {/* Reserved height keeps the cards from jumping when a later column's notes appear during the reveal. */}
                <div className="sm:min-h-24">
                  {hasHits && (
                    <>
                      <p className={`mb-2 ${captionClass}`}>{columnCaption(mode)}</p>
                      {mode === "keyword" && <p className={`mb-2 ${captionClass}`}>{RANK_ONLY_NOTE}</p>}
                      {mode === "hybrid" && <p className={`mb-2 ${captionClass}`}>{HYBRID_NOTE}</p>}
                    </>
                  )}
                </div>
                <div>
                {!col || col.state === "loading" ? (
                  <Notice>Searching…</Notice>
                ) : col.state === "error" ? (
                  <div>
                    <p role="alert" className="mb-2 text-sm text-danger">
                      {col.message}
                    </p>
                    <button
                      type="button"
                      aria-label={`Retry ${label}`}
                      className={buttonClass({ variant: "secondary" })}
                      onClick={() => {
                        setFloor(revealed);
                        setRetried((cur) => new Set(cur).add(mode));
                        runModes(submitted, [mode]);
                      }}
                    >
                      Try again
                    </button>
                  </div>
                ) : col.hits.length === 0 ? (
                  <p className={`${emptyClass} text-sm text-muted`}>No results.</p>
                ) : (
                  <>
                  <ol aria-label={`${label} results`} className="space-y-3">
                    {col.hits.map((h, n) => (
                      <li key={h.chunk_id} className={`${cardClass} text-sm`}>
                        <p className="text-xs font-medium" title={RANK_HELP}>
                          {whyListed(h, mode)}
                        </p>
                        <div className="mt-1 flex flex-wrap items-baseline gap-x-2">
                          <span className="text-muted">#{n + 1}</span>
                          <span className="min-w-0 break-words font-medium">{h.document_title}</span>
                        </div>
                        {showsSimilarity(mode) && h.score !== null && (
                          <p className={captionClass} title={SIMILARITY_HELP}>
                            Similarity {h.score.toFixed(3)}
                            <span className="sr-only"> ({SIMILARITY_HELP})</span>
                          </p>
                        )}
                        {unique.get(mode)?.has(h.document_id) && (
                          <p className="mt-1 inline-block rounded-md bg-info px-2 py-0.5 text-xs text-info-fg">
                            Only in this list
                          </p>
                        )}
                        <p className="mt-1 break-words">{snippet(h.content)}</p>
                      </li>
                    ))}
                  </ol>
                  </>
                )}
                </div>
              </section>
            );
          })}
        </div>
        </>
      )}
    </section>
  );
}
