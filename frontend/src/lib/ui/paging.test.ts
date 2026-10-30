import { expect, test } from "vitest";
import { clampedPage, DEFAULT_PAGE_SIZE, lastPage, pagingQuery, parsePaging } from "./paging";

const q = (s: string) => parsePaging(new URLSearchParams(s));

test("defaults when absent", () => {
  expect(q("")).toEqual({ page: 1, size: DEFAULT_PAGE_SIZE });
});

test("valid page and size are kept", () => {
  expect(q("page=3&size=25")).toEqual({ page: 3, size: 25 });
});

test.each(["page=0", "page=-1", "page=abc", "page=1.5", "page=", "page=2e3", "page=9999999999", "page=%20"])("invalid %s falls back to page 1", (s) => {
  expect(q(s).page).toBe(1);
});

test.each(["size=0", "size=7", "size=100", "size=abc", "size=", "size=-10"])("invalid %s falls back to the default size", (s) => {
  expect(q(s).size).toBe(DEFAULT_PAGE_SIZE);
});

test("pagingQuery omits defaults and round-trips", () => {
  expect(pagingQuery(1, 10)).toBe("");
  expect(pagingQuery(2, 10)).toBe("?page=2");
  expect(pagingQuery(1, 25)).toBe("?size=25");
  expect(q(pagingQuery(4, 50).slice(1))).toEqual({ page: 4, size: 50 });
});

test("lastPage: 0 documents is page 1; exact multiples do not add a page", () => {
  expect(lastPage(0, 10)).toBe(1);
  expect(lastPage(24, 10)).toBe(3);
  expect(lastPage(30, 10)).toBe(3);
  expect(lastPage(31, 10)).toBe(4);
});

test("clampedPage with a total goes to the last page when past the end", () => {
  expect(clampedPage(9, 10, 24, 0)).toBe(3);
  expect(clampedPage(3, 10, 24, 4)).toBe(3);
  expect(clampedPage(2, 10, 0, 0)).toBe(1);
});

test("clampedPage without a total moves back one page only when the page is empty", () => {
  expect(clampedPage(3, 10, null, 0)).toBe(2);
  expect(clampedPage(3, 10, null, 4)).toBe(3);
  expect(clampedPage(1, 10, null, 0)).toBe(1);
});
