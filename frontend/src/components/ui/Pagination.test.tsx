import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Pagination } from "./Pagination";

const setup = (p: Partial<React.ComponentProps<typeof Pagination>> = {}) => {
  const onPage = vi.fn();
  const onSize = vi.fn();
  render(<Pagination page={2} size={25} count={25} total={53} onPage={onPage} onSize={onSize} {...p} />);
  return { onPage, onSize };
};

test("is a labelled nav landmark with the range and total", () => {
  setup({ count: 25 });
  expect(screen.getByRole("navigation", { name: "Pagination" })).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Showing 26 to 50 of 53");
});

test("the last page shows the real end of the range", () => {
  setup({ page: 3, count: 3 });
  expect(screen.getByRole("status")).toHaveTextContent("Showing 51 to 53 of 53");
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
});

test("Previous and Next call onPage; Previous is disabled on page 1", () => {
  const { onPage } = setup();
  fireEvent.click(screen.getByRole("button", { name: "Previous" }));
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(onPage.mock.calls).toEqual([[1], [3]]);
});

test("page 1: Previous disabled", () => {
  setup({ page: 1 });
  expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
});

test("page-size select offers 10, 25 and 50 and reports the choice", () => {
  const { onSize } = setup();
  const select = screen.getByLabelText("Per page");
  expect(Array.from((select as HTMLSelectElement).options).map((o) => o.value)).toEqual(["10", "25", "50"]);
  expect(select).toHaveValue("25");
  fireEvent.change(select, { target: { value: "50" } });
  expect(onSize).toHaveBeenCalledWith(50);
});

test("without a total: 'Page N', Next only when the page is full", () => {
  setup({ total: null, count: 25 });
  expect(screen.getByRole("status")).toHaveTextContent("Page 2");
  expect(screen.getByRole("status")).not.toHaveTextContent(/of \d/);
  expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
});

test("without a total and a short page, Next is disabled", () => {
  setup({ total: null, count: 7 });
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
});
