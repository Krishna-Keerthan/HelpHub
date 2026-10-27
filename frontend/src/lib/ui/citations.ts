const WHITESPACE = /^\s+|\s+$/g;

/**
 * Source numbers cited in an answer that really exist. Port of backend `parse_citations`
 * (backend/app/services/prompts.py): bracket groups in ASCII, fullwidth or lenticular form,
 * comma-separated ASCII-digit parts, 1..nSources, unique, ascending. The server does not store `cited`,
 * so a restored conversation recomputes it with this. Known gap: Python `str.strip()` and JS whitespace
 * differ on a few exotic characters (decisions.md D15).
 */
export function parseCitations(answer: string, nSources: number): number[] {
  const cited = new Set<number>();
  for (const m of answer.matchAll(/[\[［【]([^\[［【\]］】]*)[\]］】]/g)) {
    for (const raw of m[1]!.split(",")) {
      const part = raw.replace(WHITESPACE, "");
      if (/^[0-9]+$/.test(part)) {
        const n = Number(part);
        if (n >= 1 && n <= nSources) cited.add(n);
      }
    }
  }
  return [...cited].sort((a, b) => a - b);
}
