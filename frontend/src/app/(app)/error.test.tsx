import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import AppError from "./error";

test("shows a short message and Try again calls reset", () => {
  const reset = vi.fn();
  render(<AppError error={new Error("secret db detail")} reset={reset} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(reset).toHaveBeenCalledTimes(1);
});

test("never shows the error message or stack", () => {
  const error = new Error("secret db detail");
  render(<AppError error={error} reset={() => {}} />);
  expect(document.body).not.toHaveTextContent("secret db detail");
  expect(document.body).not.toHaveTextContent(/at .*\.tsx?:\d+/);
});
