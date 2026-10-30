export const PAGE_SIZES = [10, 25, 50] as const;
export const DEFAULT_PAGE_SIZE = 10;

/** `?page=2&size=25`, validated: anything that is not a positive integer page or an allowed size falls back. */
export function parsePaging(params: { get(name: string): string | null }): { page: number; size: number } {
  const rawPage = params.get("page");
  const rawSize = Number(params.get("size"));
  const page = rawPage !== null && /^[1-9]\d{0,5}$/.test(rawPage) ? Number(rawPage) : 1;
  const size = (PAGE_SIZES as readonly number[]).includes(rawSize) ? rawSize : DEFAULT_PAGE_SIZE;
  return { page, size };
}

/** Query string for a page; defaults are left out so the plain URL stays clean. */
export function pagingQuery(page: number, size: number): string {
  const q = new URLSearchParams();
  if (page > 1) q.set("page", String(page));
  if (size !== DEFAULT_PAGE_SIZE) q.set("size", String(size));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const lastPage = (total: number, size: number): number => Math.max(1, Math.ceil(total / size));

/**
 * The page to show instead when the requested one came back empty past the first page (deleted
 * rows, a typed-in URL). With a total it is the last page; without one it is the previous page.
 */
export function clampedPage(page: number, size: number, total: number | null, count: number): number {
  if (total !== null) return Math.min(page, lastPage(total, size));
  return count === 0 && page > 1 ? page - 1 : page;
}
