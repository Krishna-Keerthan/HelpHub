import { act, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

const hook = vi.hoisted(() => ({ emit: undefined as ((waking: boolean) => void) | undefined }));
vi.mock("@/lib/api/authed-fetch", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/authed-fetch")>()),
  onServiceWaking: (l: (w: boolean) => void) => {
    hook.emit = l;
    return () => void (hook.emit = undefined);
  },
}));

import { StickyHeader } from "./StickyHeader";

test("the 'service is waking up' notice is inside the sticky header, so it stays in view while scrolling", () => {
  render(<StickyHeader innerClass="max-w-3xl"><span>row</span></StickyHeader>);
  const header = screen.getByRole("banner");
  expect(within(header).queryByText(/waking up/)).toBeNull();
  act(() => hook.emit!(true));
  expect(within(header).getByText(/The service is waking up/)).toBeInTheDocument();
  act(() => hook.emit!(false));
  expect(within(header).queryByText(/waking up/)).toBeNull();
});

test("the notice comes after the header's own row, not before it", () => {
  render(<StickyHeader innerClass="max-w-3xl"><span>row</span></StickyHeader>);
  act(() => hook.emit!(true));
  const header = screen.getByRole("banner");
  expect(header.firstElementChild).toHaveTextContent("row");
  expect(header.lastElementChild).toHaveTextContent("waking up");
});

test("the inner row takes the page's width rule", () => {
  render(<StickyHeader innerClass="max-w-xl custom"><span>row</span></StickyHeader>);
  expect(screen.getByRole("banner").firstElementChild!.className).toContain("max-w-xl custom");
});
