import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { StatusPill } from "./StatusPill";

test.each([
  ["READY", "bg-ok-bg"],
  ["PENDING", "bg-warn-bg"],
  ["FAILED", "bg-bad-bg"],
])("StatusPill shows %s with its own tone", (status, tone) => {
  render(<StatusPill status={status} />);
  expect(screen.getByText(status).className).toContain(tone);
});

test("StatusPill falls back to the neutral tone for an unknown status and still shows the text", () => {
  render(<StatusPill status="ARCHIVED" />);
  const pill = screen.getByText("ARCHIVED");
  expect(pill.className).toContain("bg-chip");
  expect(pill.className).not.toContain("bg-ok-bg");
});
