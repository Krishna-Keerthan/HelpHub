import { screen, within } from "@testing-library/react";
import { render } from "@/test/render";
import { afterEach, expect, test, vi } from "vitest";
import { getQueryClient } from "@/lib/query/client";
import { queryKeys } from "@/lib/query/hooks";
import AppLayout from "./layout";

test("shell has a skip link first, then banner, labelled navigation and a focusable main", () => {
  render(
    <AppLayout>
      <p>content</p>
    </AppLayout>,
  );
  const skip = screen.getByRole("link", { name: "Skip to content" });
  expect(skip).toHaveAttribute("href", "#content");
  expect(screen.getByRole("banner")).toBeInTheDocument();
  const nav = screen.getByRole("navigation", { name: "Main" });
  expect(nav).toHaveTextContent("Documents");
  expect(nav).toHaveTextContent("Chat");
  expect(screen.getByRole("link", { name: "Compare" })).toHaveAttribute("href", "/compare");
  expect(screen.getByRole("main")).toHaveAttribute("id", "content");
  // DOM order = tab order: skip link precedes the header.
  const all = Array.from(document.body.querySelectorAll("a, button"));
  expect(all[0]).toBe(skip);
});

test("main is widened only for pages that mark themselves wide", () => {
  render(<AppLayout><p>content</p></AppLayout>);
  expect(screen.getByRole("main").className).toContain("max-w-3xl");
  expect(screen.getByRole("main").className).toContain("has-[[data-wide]]:max-w-5xl");
});

test("header renders all three section links in order, each inside the labelled navigation", () => {
  render(<AppLayout><p>content</p></AppLayout>);
  const links = within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link");
  expect(links.map((l) => l.textContent)).toEqual(["Home", "Documents", "Chat", "Compare"]);
  expect(links.map((l) => l.getAttribute("href"))).toEqual(["/home", "/documents", "/chat", "/compare"]);
});

test("the nav is not a scroll container, so focus rings cannot be clipped", () => {
  render(<AppLayout><p>content</p></AppLayout>);
  expect(screen.getByRole("navigation", { name: "Main" }).className).not.toMatch(/overflow/);
  expect(screen.getByRole("banner").innerHTML).not.toMatch(/overflow/);
});

test("header order: skip link first, then the brand, the nav links, then the theme toggle, then Log out", () => {
  render(<AppLayout><p>content</p></AppLayout>);
  const order = Array.from(document.body.querySelectorAll("a, button")).map((el) => el.getAttribute("aria-label") ?? el.textContent);
  expect(order).toEqual([
    "Skip to content", "HelpHub", "Home", "Documents", "Chat", "Compare", "Switch to dark theme", "Log out", "Home", "GitHub",
  ]);
});

test("the brand links to /documents", () => {
  render(<AppLayout><p>content</p></AppLayout>);
  expect(within(screen.getByRole("banner")).getByRole("link", { name: "HelpHub" })).toHaveAttribute("href", "/documents");
});

afterEach(() => vi.unstubAllEnvs());

test("the shell has a footer after main with GitHub, Contact and Home links", () => {
  vi.stubEnv("NEXT_PUBLIC_CONTACT_EMAIL", "beta@example.test");
  render(<AppLayout><p>content</p></AppLayout>);
  const footer = screen.getByRole("contentinfo");
  expect(footer).toHaveTextContent("Built by Krishna Keerthan K");
  expect(within(footer).getByRole("link", { name: "GitHub" })).toHaveAttribute("href", "https://github.com/Krishna-Keerthan/HelpHub");
  expect(within(footer).getByRole("link", { name: "Contact" })).toHaveAttribute("href", "mailto:beta@example.test");
  expect(within(footer).getByRole("link", { name: "Home" })).toHaveAttribute("href", "/home");
  expect(screen.getByRole("main").compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("the footer is a column bottom (min-height layout) and follows the same width rule as main", () => {
  render(<AppLayout><p>content</p></AppLayout>);
  const shell = screen.getByRole("main").parentElement!;
  expect(shell.className).toContain("min-h-screen");
  expect(shell.className).toContain("flex-col");
  expect(screen.getByRole("main").className).toContain("flex-1");
  const box = screen.getByRole("contentinfo").parentElement!;
  expect(box.className).toContain("max-w-3xl");
  expect(box.className).toContain("group-has-[[data-wide]]/shell:max-w-5xl");
});

test("phone header is two rows: brand and the actions (chip, theme, Log out) on row one, the full-width nav on row two", () => {
  getQueryClient().setQueryData(queryKeys.me, { role: "agent", email: "ada@example.test" });
  render(<AppLayout><p>content</p></AppLayout>);
  const nav = screen.getByRole("navigation", { name: "Main" });
  expect(nav.className).toContain("basis-full"); // its own row
  const actions = screen.getByRole("button", { name: "Log out" }).parentElement!;
  expect(actions).toContainElement(screen.getByText("agent")); // the chip is beside the toggle and Log out
  expect(actions).toContainElement(screen.getByRole("button", { name: /theme/i }));
  expect(actions.className).toContain("ml-auto");
  expect(actions.className).toContain("min-w-0"); // may shrink, so a long email truncates instead of wrapping to a third row
  expect(nav.className).toContain("order-3");
  expect(actions.className).toContain("order-2");
  // Nothing else in the header is placed on its own full-width row.
  const fullRow = Array.from(screen.getByRole("banner").querySelectorAll("*")).filter((e) => e.className.toString().split(" ").includes("basis-full"));
  expect(fullRow).toEqual([nav]);
});

test("tap targets: brand, nav links and Log out are at least 40 px tall (min-h-10)", () => {
  render(<AppLayout><p>content</p></AppLayout>);
  const header = within(screen.getByRole("banner"));
  for (const el of [header.getByRole("link", { name: "HelpHub" }), header.getByRole("link", { name: "Home" }), header.getByRole("button", { name: "Log out" })]) {
    expect(el.className).toContain("min-h-10");
  }
});
