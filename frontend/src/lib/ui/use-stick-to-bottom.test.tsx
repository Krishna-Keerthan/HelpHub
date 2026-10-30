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

/** Put the end marker `px` below the bottom of an 800 px tall screen (negative: on screen), then scroll. */
function markerBelowFold(px: number) {
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ top: 800 + px } as DOMRect);
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
  markerBelowFold(1200);
  rerender(<Probe k={2} />);
  rerender(<Probe k={3} />);
  expect(scrollIntoView).not.toHaveBeenCalled();
});

test("follows again once the reader is back within the threshold", () => {
  const { rerender } = render(<Probe k={1} />);
  markerBelowFold(1200);
  rerender(<Probe k={2} />);
  scrollIntoView.mockClear();
  markerBelowFold(NEAR_BOTTOM_PX - 1);
  rerender(<Probe k={3} />);
  expect(scrollIntoView).toHaveBeenCalledTimes(1);
});

test("exactly at the threshold still follows; one pixel beyond does not", () => {
  const { rerender } = render(<Probe k={1} />);
  markerBelowFold(NEAR_BOTTOM_PX);
  scrollIntoView.mockClear();
  rerender(<Probe k={2} />);
  expect(scrollIntoView).toHaveBeenCalledTimes(1);
  markerBelowFold(NEAR_BOTTOM_PX + 1);
  scrollIntoView.mockClear();
  rerender(<Probe k={3} />);
  expect(scrollIntoView).not.toHaveBeenCalled();
});

test("follow() re-arms it after the reader had scrolled up", () => {
  const { rerender } = render(<Probe k={1} />);
  markerBelowFold(2000);
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

test("a tall footer, composer or padding below the last message does not make the reader look scrolled up", () => {
  // The document is 10,000 px tall (footer and all) but the marker is on screen: still following.
  vi.spyOn(document.documentElement, "scrollHeight", "get").mockReturnValue(10_000);
  const { rerender } = render(<Probe k={1} />);
  markerBelowFold(-40); // 40 px above the bottom edge of the screen, i.e. visible
  scrollIntoView.mockClear();
  rerender(<Probe k={2} />);
  expect(scrollIntoView).toHaveBeenCalledTimes(1);
});
