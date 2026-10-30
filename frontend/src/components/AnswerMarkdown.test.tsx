import { render, screen, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

// A pass-through spy on the real renderer, to count how often Markdown is actually rendered.
const markdown = vi.hoisted(() => vi.fn());
vi.mock("react-markdown", async (orig) => {
  const real = (await orig<typeof import("react-markdown")>()).default;
  return { default: (props: Parameters<typeof real>[0]) => (markdown(), real(props)) };
});
beforeEach(() => markdown.mockClear());
import { AnswerMarkdown } from "./AnswerMarkdown";

const show = (text: string) => render(<AnswerMarkdown text={text} />);

test("bullets become a list", () => {
  show("Steps:\n\n* first\n* second\n");
  const items = within(screen.getByRole("list")).getAllByRole("listitem");
  expect(items.map((i) => i.textContent)).toEqual(["first", "second"]);
});

test("numbered lists become an ordered list", () => {
  const { container } = show("1. one\n2. two\n");
  expect(container.querySelector("ol")).not.toBeNull();
});

test("**bold** becomes <strong> and `code` becomes <code>", () => {
  const { container } = show("Refunds take **five days** via `card`.");
  expect(container.querySelector("strong")).toHaveTextContent("five days");
  expect(container.querySelector("code")).toHaveTextContent("card");
  expect(container).not.toHaveTextContent("**");
});

test("a [n] citation marker stays visible text, also in its fullwidth forms", () => {
  const { container } = show("Five days [4]. Also ［2］ and 【3】.");
  expect(container).toHaveTextContent("Five days [4]. Also [2] and [3].");
});

test("<script> and <img onerror> strings are shown as text or dropped, never as elements", () => {
  const { container } = show('Hi <script>alert(1)</script> and <img src=x onerror="alert(2)"> done\n\n<b onclick="x()">raw</b>');
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("img")).toBeNull();
  expect(container.querySelector("b")).toBeNull();
  expect(container.querySelector("[onerror]")).toBeNull();
  expect(container.querySelector("[onclick]")).toBeNull();
});

test("markdown image syntax is not turned into an <img> (nothing is fetched)", () => {
  const { container } = show("![tracker](https://evil.test/p.png)");
  expect(container.querySelector("img")).toBeNull();
});

test.each([
  ["javascript:", "[x](javascript:alert(1))"],
  ["JaVaScRiPt:", "[x](JaVaScRiPt:alert(1))"],
  ["data:", "[x](data:text/html;base64,PHNjcmlwdD4=)"],
  ["vbscript:", "[x](vbscript:msgbox(1))"],
  ["relative", "[x](/documents)"],
])("a %s link is not an <a href>", (_n, md) => {
  const { container } = show(md);
  expect(container.querySelector("a")).toBeNull();
  expect(container).toHaveTextContent("x");
});

test("http(s) and mailto links open in a new tab with rel noopener noreferrer", () => {
  show("[a](https://example.test/a) [b](http://example.test/b) [c](mailto:x@example.test)");
  for (const name of ["a", "b", "c"]) {
    const link = screen.getByRole("link", { name });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  }
  expect(screen.getByRole("link", { name: "a" })).toHaveAttribute("href", "https://example.test/a");
});

test("headings are plain emphasised paragraphs", () => {
  const { container } = show("# Title\n\ntext");
  expect(container.querySelector("h1")).toBeNull();
  expect(container).toHaveTextContent("Title");
});

test("single newlines inside a paragraph still break the line", () => {
  const { container } = show("line one\nline two");
  expect(container.querySelector("p")!.className).toContain("whitespace-pre-line");
});

test("memoised by text: the same text does not render Markdown again, new text does", () => {
  const { rerender } = show("same");
  expect(markdown).toHaveBeenCalledTimes(1);
  rerender(<AnswerMarkdown text="same" />);
  expect(markdown).toHaveBeenCalledTimes(1);
  rerender(<AnswerMarkdown text="same and more" />);
  expect(markdown).toHaveBeenCalledTimes(2);
});
