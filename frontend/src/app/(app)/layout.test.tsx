import { screen, within } from "@testing-library/react";
import { render } from "@/test/render";
import { expect, test } from "vitest";
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
  expect(order).toEqual(["Skip to content", "HelpHub", "Home", "Documents", "Chat", "Compare", "Switch to dark theme", "Log out"]);
});

test("the brand links to /documents", () => {
  render(<AppLayout><p>content</p></AppLayout>);
  expect(within(screen.getByRole("banner")).getByRole("link", { name: "HelpHub" })).toHaveAttribute("href", "/documents");
});
