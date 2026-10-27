import { act, fireEvent, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ThemeToggle } from "./ThemeToggle";

function stubOsDark(dark: boolean) {
  const listeners = new Set<() => void>();
  const state = { dark };
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: q.includes("dark") ? state.dark : false,
    addEventListener: (_: string, f: () => void) => listeners.add(f),
    removeEventListener: (_: string, f: () => void) => listeners.delete(f),
  }));
  return {
    set(next: boolean) {
      state.dark = next;
      listeners.forEach((f) => f());
    },
  };
}

beforeEach(() => {
  delete document.documentElement.dataset.theme;
  document.cookie = "hh_theme=; Path=/; Max-Age=0";
});
afterEach(() => {
  delete document.documentElement.dataset.theme;
  document.cookie = "hh_theme=; Path=/; Max-Age=0";
});

test("with no cookie and an OS in dark mode it offers the light theme", () => {
  stubOsDark(true);
  render(<ThemeToggle />);
  expect(screen.getByRole("button", { name: "Switch to light theme" })).toBeInTheDocument();
});

test("with no cookie and an OS in light mode it offers the dark theme", () => {
  stubOsDark(false);
  render(<ThemeToggle />);
  expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
});

test("an explicit data-theme wins over the OS", () => {
  stubOsDark(true);
  document.documentElement.dataset.theme = "light";
  render(<ThemeToggle />);
  expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
});

test("clicking sets the cookie and data-theme and flips the label, without a reload", () => {
  stubOsDark(false);
  render(<ThemeToggle />);
  fireEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(document.cookie).toContain("hh_theme=dark");
  expect(screen.getByRole("button", { name: "Switch to light theme" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(document.cookie).toContain("hh_theme=light");
  expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
});

test("with no explicit choice the label follows a change of the OS setting", () => {
  const os = stubOsDark(false);
  render(<ThemeToggle />);
  expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
  act(() => os.set(true));
  expect(screen.getByRole("button", { name: "Switch to light theme" })).toBeInTheDocument();
});

test("the server render is a same-size placeholder with no button, so hydration cannot mismatch", () => {
  stubOsDark(true);
  const html = renderToString(<ThemeToggle />);
  expect(html).not.toContain("<button");
  expect(html).toContain("theme-toggle-placeholder");
  expect(html).toContain("h-10 w-10");
});

test("the button is at least 40px wide and tall and its icon is hidden from assistive tech", () => {
  stubOsDark(false);
  render(<ThemeToggle />);
  const button = screen.getByRole("button", { name: "Switch to dark theme" });
  expect(button.className).toContain("min-h-10");
  expect(button.className).toContain("min-w-10");
  expect(button.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
});
