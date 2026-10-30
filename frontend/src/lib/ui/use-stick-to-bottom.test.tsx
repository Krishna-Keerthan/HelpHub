import { render } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { NEAR_BOTTOM_PX, useStickToBottom } from "./use-stick-to-bottom";

const scrollIntoView = vi.fn();
beforeEach(() => {
  scrollIntoView.mockClear();
  Element.prototype.scrollIntoView = scrollIntoView;
});
afterEach(() => vi.restoreAllMocks());

/** Pretend the page is `height` tall, the window is 800 tall and scrolled to `y`. */
function page(height: number, y: number) {
  vi.spyOn(document.documentElement, "scrollHeight", "get").mockReturnValue(height);
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 });
  Object.defineProperty(window, "scrollY", { configurable: true, value: y });
  window.dispatchEvent(new Event("scroll"));
}

const handle: { follow?: () => void } = {};
function Probe({ k, enabled = true }: { k: number; enabled?: boolean }) {
  const { endRef, follow } = useStickToBottom(k, enabled);
  useEffect(() => {
    handle.follow = follow;
  });
  return <div ref={endRef} />;
}

test("scrolls the end marker into view when the content changes and the reader is at the bottom", () => {
  const { rerender } = render(<Probe k={1} />);
  expect(scrollIntoView).toHaveBeenCalledTimes(1); // first paint: nothing was scrolled up yet
  rerender(<Probe k={2} />);
  expect(scrollIntoView).toHaveBeenCalledTimes(2);
  expect(scrollIntoView).toHaveBeenLastCalledWith({ block: "end" });
});

test("does not scroll while the reader is further than the threshold from the bottom", () => {
  const { rerender } = render(<Probe k={1} />);
  scrollIntoView.mockClear();
  page(3000, 1000); // 3000 - (1000 + 800) = 1200 px from the bottom
  rerender(<Probe k={2} />);
  rerender(<Probe k={3} />);
  expect(scrollIntoView).not.toHaveBeenCalled();
});

test("follows again once the reader is back within the threshold", () => {
  const { rerender } = render(<Probe k={1} />);
  page(3000, 1000);
  rerender(<Probe k={2} />);
  scrollIntoView.mockClear();
  page(3000, 3000 - 800 - (NEAR_BOTTOM_PX - 1));
  rerender(<Probe k={3} />);
  expect(scrollIntoView).toHaveBeenCalledTimes(1);
});

test("exactly at the threshold still follows; one pixel beyond does not", () => {
  const { rerender } = render(<Probe k={1} />);
  page(3000, 3000 - 800 - NEAR_BOTTOM_PX);
  scrollIntoView.mockClear();
  rerender(<Probe k={2} />);
  expect(scrollIntoView).toHaveBeenCalledTimes(1);
  page(3000, 3000 - 800 - NEAR_BOTTOM_PX - 1);
  scrollIntoView.mockClear();
  rerender(<Probe k={3} />);
  expect(scrollIntoView).not.toHaveBeenCalled();
});

test("follow() re-arms it after the reader had scrolled up", () => {
  const { rerender } = render(<Probe k={1} />);
  page(3000, 0);
  scrollIntoView.mockClear();
  handle.follow!();
  rerender(<Probe k={2} />);
  expect(scrollIntoView).toHaveBeenCalledTimes(1);
});

test("does nothing while disabled (nothing to show yet)", () => {
  render(<Probe k={1} enabled={false} />);
  expect(scrollIntoView).not.toHaveBeenCalled();
});

test("removes its scroll listener on unmount", () => {
  const remove = vi.spyOn(window, "removeEventListener");
  render(<Probe k={1} />).unmount();
  expect(remove).toHaveBeenCalledWith("scroll", expect.any(Function));
});
