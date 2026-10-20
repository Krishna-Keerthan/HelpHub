import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Notice } from "./Notice";

test("informational notices are polite status regions, not alerts", () => {
  render(<Notice>Waking up</Notice>);
  const el = screen.getByRole("status");
  expect(el).toHaveAttribute("aria-live", "polite");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
