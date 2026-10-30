import { render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import NotFound from "./not-found";

test("branded 404: brand, message, links to Home and Documents", () => {
  render(<NotFound />);
  expect(screen.getByText("HelpHub")).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("This page could not be found.");
  // The page body's own links; the header and footer have a Home link of their own.
  const body = within(screen.getByRole("main"));
  expect(body.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/home");
  expect(body.getByRole("link", { name: "Documents" })).toHaveAttribute("href", "/documents");
});
