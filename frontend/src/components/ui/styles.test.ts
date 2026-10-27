import { expect, test } from "vitest";
import { buttonClass, chipClass } from "./styles";

test("each button variant has its own look and every one is at least 40px tall", () => {
  const classes = (["primary", "secondary", "ghost", "danger"] as const).map((variant) => buttonClass({ variant }));
  expect(new Set(classes).size).toBe(4);
  for (const c of classes) expect(c).toContain("min-h-10");
  expect(buttonClass({ variant: "primary" })).toContain("bg-accent");
  expect(buttonClass({ variant: "secondary" })).toContain("border-control-border");
  expect(buttonClass({ variant: "danger" })).toContain("text-danger");
});

test("buttonClass defaults to secondary, and block and label are opt-in", () => {
  expect(buttonClass()).toBe(buttonClass({ variant: "secondary" }));
  expect(buttonClass()).not.toContain("w-full");
  expect(buttonClass({ block: true })).toContain("w-full");
  expect(buttonClass()).not.toContain("focus-within:outline-2");
  expect(buttonClass({ label: true })).toContain("focus-within:outline-2");
});

test("hover styles never apply to a disabled button", () => {
  expect(buttonClass({ variant: "primary" })).toContain("not-disabled:hover:");
  expect(buttonClass({ variant: "primary" })).not.toMatch(/(^| )hover:/);
});

test("chips: the in-answer size is smaller than the suggestion size", () => {
  expect(chipClass("sm")).toContain("min-h-8");
  expect(chipClass("md")).toContain("min-h-10");
});
