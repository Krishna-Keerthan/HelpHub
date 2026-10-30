import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import NotFound from "./not-found";

test("branded 404: brand, message, links to Home and Documents", () => {
  render(<NotFound />);
  expect(screen.getByText("HelpHub")).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("This page could not be found.");
  expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/home");
  expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute("href", "/documents");
});
