import { render, screen } from "@testing-library/react";
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
  expect(screen.getByRole("main")).toHaveAttribute("id", "content");
  // DOM order = tab order: skip link precedes the header.
  const all = Array.from(document.body.querySelectorAll("a, button"));
  expect(all[0]).toBe(skip);
});
