import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { RequestAccessLink } from "./RequestAccessLink";

test("renders the mailto link when a contact email is set", () => {
  render(<RequestAccessLink contactEmail="beta@example.test" />);
  expect(screen.getByRole("link", { name: "Request access" })).toHaveAttribute("href", expect.stringContaining("mailto:beta@example.test?subject=HelpHub%20access%20request"));
});

test("renders nothing when the variable is missing", () => {
  const { container } = render(<RequestAccessLink contactEmail={undefined} />);
  expect(container).toBeEmptyDOMElement();
});
