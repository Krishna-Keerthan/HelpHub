import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { COPY_TIMEOUT_MS, CopyAnswerButton } from "./CopyAnswerButton";

function clipboard(writeText: (t: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
}
/** A writeText that stays pending until the test settles it. */
function pending() {
  let resolve!: () => void;
  let reject!: (e: Error) => void;
  const promise = new Promise<void>((res, rej) => ((resolve = res), (reject = rej)));
  const writeText = vi.fn(() => promise);
  clipboard(writeText);
  return { writeText, resolve, reject };
}
const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
const note = () => screen.getByRole("status").textContent;
const click = () => fireEvent.click(screen.getByRole("button", { name: "Copy" }));

beforeEach(() => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] }));
afterEach(() => {
  vi.useRealTimers();
  Reflect.deleteProperty(navigator, "clipboard");
});

test("a promise that never settles shows 'Could not copy' after 3 seconds, not before", async () => {
  pending();
  render(<CopyAnswerButton text="hello" />);
  click();
  await tick(COPY_TIMEOUT_MS - 1);
  expect(note()).toBe("");
  await tick(1);
  expect(note()).toBe("Could not copy");
});

test("a late resolution does not overwrite the message after the timeout fired", async () => {
  const p = pending();
  render(<CopyAnswerButton text="hello" />);
  click();
  await tick(COPY_TIMEOUT_MS);
  expect(note()).toBe("Could not copy");
  await act(async () => p.resolve());
  expect(note()).toBe("Could not copy");
  expect(screen.queryByText("Copied")).toBeNull();
});

test("a late rejection after the timeout changes nothing either", async () => {
  const p = pending();
  render(<CopyAnswerButton text="hello" />);
  click();
  await tick(COPY_TIMEOUT_MS);
  await act(async () => p.reject(new Error("denied")));
  expect(note()).toBe("Could not copy");
});

test("copying that finishes in time says 'Copied', and the timeout does not turn it into a failure later", async () => {
  const p = pending();
  render(<CopyAnswerButton text="hello" />);
  click();
  await tick(1000);
  await act(async () => p.resolve());
  expect(note()).toBe("Copied");
  expect(p.writeText).toHaveBeenCalledWith("hello");
  await tick(COPY_TIMEOUT_MS); // past the old deadline; the note has also timed out by now
  expect(screen.queryByText("Could not copy")).toBeNull();
});

test("a rejection says 'Could not copy' at once", async () => {
  const p = pending();
  render(<CopyAnswerButton text="hello" />);
  click();
  await act(async () => p.reject(new Error("denied")));
  expect(note()).toBe("Could not copy");
});

test("the message goes away after a moment", async () => {
  clipboard(async () => {});
  render(<CopyAnswerButton text="hello" />);
  click();
  await tick(0);
  expect(note()).toBe("Copied");
  await tick(2000);
  expect(note()).toBe("");
});

test("a newer click wins over an older attempt that is still pending", async () => {
  const first = pending();
  render(<CopyAnswerButton text="one" />);
  click();
  await tick(1000);
  const second = pending(); // the next click uses a working clipboard
  second.resolve();
  click();
  await tick(0);
  expect(note()).toBe("Copied");
  await tick(COPY_TIMEOUT_MS); // the first attempt's deadline passes
  await act(async () => first.reject(new Error("late")));
  expect(screen.queryByText("Could not copy")).toBeNull();
});

test("unmounting with an attempt pending shows nothing and leaves no timer running afterwards", async () => {
  pending();
  const view = render(<CopyAnswerButton text="hello" />);
  click();
  view.unmount();
  await tick(COPY_TIMEOUT_MS * 2);
  expect(vi.getTimerCount()).toBe(0);
});

test("without the Clipboard API nothing is rendered", () => {
  const { container } = render(<CopyAnswerButton text="hello" />);
  expect(container).toBeEmptyDOMElement();
});
