import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import Home from "./page";

test("home renders the product name", () => {
  render(<Home />);
  expect(screen.getByRole("heading", { name: "HelpHub" })).toBeInTheDocument();
});
