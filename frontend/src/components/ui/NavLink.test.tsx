import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

const pathname = vi.hoisted(() => ({ value: null as string | null }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.value }));

import { NavLink } from "./NavLink";

afterEach(() => {
  pathname.value = null;
});

test("NavLink is current on an exact path match", () => {
  pathname.value = "/documents";
  render(<NavLink href="/documents">Documents</NavLink>);
  expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute("aria-current", "page");
});

test("NavLink stays current on a sub-route", () => {
  pathname.value = "/documents/abc";
  render(<NavLink href="/documents">Documents</NavLink>);
  expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute("aria-current", "page");
});

test("NavLink is not current on a different path or a path that only shares a prefix", () => {
  pathname.value = "/chatter";
  render(<NavLink href="/chat">Chat</NavLink>);
  expect(screen.getByRole("link", { name: "Chat" })).not.toHaveAttribute("aria-current");
});

test("NavLink with a null pathname is not current and does not throw", () => {
  pathname.value = null;
  render(<NavLink href="/compare">Compare</NavLink>);
  expect(screen.getByRole("link", { name: "Compare" })).not.toHaveAttribute("aria-current");
});

test("the active link looks different from an inactive one", () => {
  pathname.value = "/chat";
  render(
    <>
      <NavLink href="/chat">Chat</NavLink>
      <NavLink href="/compare">Compare</NavLink>
    </>,
  );
  expect(screen.getByRole("link", { name: "Chat" }).className).not.toBe(screen.getByRole("link", { name: "Compare" }).className);
});

test("NavLink is tighter below sm (px-2) so five items fit one row at 390 px, and keeps a 40 px tap height", () => {
  pathname.value = "/";
  render(<NavLink href="/chat">Chat</NavLink>);
  const cls = screen.getByRole("link", { name: "Chat" }).className.split(" ");
  expect(cls).toContain("px-2");
  expect(cls).toContain("sm:px-3");
  expect(cls).not.toContain("px-3");
  expect(cls).toContain("min-h-10");
});
