import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { DEMO_QUERIES } from "@/lib/demo-queries";
import { CONVERSATION_STORAGE } from "@/lib/session/storage";
import { render } from "@/test/render";
import { routeFetch, sse } from "@/test/fetch-mock";
import { ChatView } from "./ChatView";

const ID = "11111111-1111-1111-1111-111111111111";
const HISTORY = `GET /api/conversations/${ID}/messages`;
const row = (role: string, content: string) => ({
  id: `m-${content}`, role, content, status: "complete", sources: [], model: null, created_at: "2026-01-01T00:00:00Z",
});
const done = (id = "c1") => ["done", { conversation_id: id, status: "complete", cited: [] }] as [string, object];

const box = () => screen.getByLabelText("Your question") as HTMLTextAreaElement;
const form = () => screen.getByRole("form", { name: "Ask a question" });
const type = (text: string) => fireEvent.change(box(), { target: { value: text } });
const ask = (text: string) => {
  type(text);
  fireEvent.submit(form());
};
const abortError = () => new DOMException("The user aborted a request.", "AbortError");

/** A chat stream that stays open until the test ends it; it errors like a browser does when its request is aborted. */
function openStream() {
  const enc = new TextEncoder();
  const state = { signal: undefined as AbortSignal | undefined, controller: undefined as ReadableStreamDefaultController<Uint8Array> | undefined };
  const push = (event: string, data: object) => state.controller!.enqueue(enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
  const handler = (req: Request) => {
    state.signal = req.signal;
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        state.controller = c;
        req.signal.addEventListener("abort", () => c.error(abortError()));
      },
    });
    return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
  };
  return { state, push, handler };
}

let rejections: unknown[] = [];
const onRejection = (reason: unknown) => void rejections.push(reason);
const scrollIntoView = vi.fn();
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 30)); });

beforeEach(() => {
  rejections = [];
  process.on("unhandledRejection", onRejection);
  scrollIntoView.mockClear();
  Element.prototype.scrollIntoView = scrollIntoView;
});
afterEach(() => {
  process.off("unhandledRejection", onRejection);
  vi.restoreAllMocks();
  Reflect.deleteProperty(navigator, "clipboard");
});

// ---- messages -------------------------------------------------------------------------------------------

test("each exchange has visible You and HelpHub labels; the answer sits in a card, the question in a tinted bubble", async () => {
  routeFetch({ "POST /api/chat/stream": () => sse(["token", { text: "Five days." }], done()) });
  render(<ChatView />);
  ask("refunds?");
  await screen.findByText("Five days.");
  const item = within(screen.getByRole("list", { name: "Conversation" })).getAllByRole("listitem")[0]!;
  expect(within(item).getByText("You")).toBeVisible();
  expect(within(item).getByText("HelpHub")).toBeVisible();
  const question = within(item).getByText("refunds?");
  const answerCard = within(item).getByText("Five days.").closest("div.border")!;
  expect(question.className).toContain("bg-chip");
  expect(answerCard.className).toContain("bg-surface-raised");
  expect(answerCard).not.toContainElement(question);
});

// ---- composer -------------------------------------------------------------------------------------------

test("the question box is a multi-line textarea in a form pinned to the bottom of the screen", () => {
  render(<ChatView />);
  expect(box().tagName).toBe("TEXTAREA");
  expect(box()).toHaveAttribute("maxlength", "2000");
  expect(form().className).toContain("sticky");
  expect(form().className).toContain("bottom-0");
});

test("Enter sends the message and clears the box", async () => {
  const f = routeFetch({ "POST /api/chat/stream": () => sse(["token", { text: "ok" }], done()) });
  render(<ChatView />);
  type("hello");
  fireEvent.keyDown(box(), { key: "Enter" });
  await screen.findByText("ok");
  expect(await f.calls[0]!.req.json()).toMatchObject({ message: "hello" });
  expect(box()).toHaveValue("");
});

test("Shift+Enter does not send", async () => {
  const f = routeFetch({ "POST /api/chat/stream": () => sse(done()) });
  render(<ChatView />);
  type("line one");
  const notPrevented = fireEvent.keyDown(box(), { key: "Enter", shiftKey: true });
  await flush();
  expect(notPrevented).toBe(true); // the browser's default (a newline) was not blocked
  expect(f.calls).toHaveLength(0);
  expect(box()).toHaveValue("line one");
});

test("Enter while an input method is composing text does not send", async () => {
  const f = routeFetch({ "POST /api/chat/stream": () => sse(done()) });
  render(<ChatView />);
  type("日本");
  fireEvent.keyDown(box(), { key: "Enter", isComposing: true });
  await flush();
  expect(f.calls).toHaveLength(0);
});

test("Enter on an empty or whitespace-only box sends nothing", async () => {
  const f = routeFetch({ "POST /api/chat/stream": () => sse(done()) });
  render(<ChatView />);
  fireEvent.keyDown(box(), { key: "Enter" });
  type("   ");
  fireEvent.keyDown(box(), { key: "Enter" });
  await flush();
  expect(f.calls).toHaveLength(0);
});

test("while an answer streams, Ask is disabled, Enter sends nothing more, and Stop is shown", async () => {
  const s = openStream();
  const f = routeFetch({ "POST /api/chat/stream": s.handler });
  render(<ChatView />);
  ask("first");
  await waitFor(() => expect(s.state.controller).toBeDefined());
  expect(screen.getByRole("button", { name: "Answering…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Stop" })).toBeEnabled();
  type("second");
  fireEvent.keyDown(box(), { key: "Enter" });
  await flush();
  expect(f.calls).toHaveLength(1);
  expect(box()).toHaveValue("second"); // typing ahead is kept
});

// ---- Stop -----------------------------------------------------------------------------------------------

test("Stop aborts the request, keeps the partial answer, says 'Stopped.' and re-enables Ask", async () => {
  const s = openStream();
  routeFetch({ "POST /api/chat/stream": s.handler });
  render(<ChatView />);
  ask("long question");
  await waitFor(() => expect(s.state.controller).toBeDefined());
  s.push("token", { text: "Partial " });
  s.push("token", { text: "answer" });
  await screen.findByText("Partial answer");
  expect(s.state.signal!.aborted).toBe(false);

  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  expect(s.state.signal!.aborted).toBe(true);
  await flush();
  expect(screen.getByText("Partial answer")).toBeInTheDocument();
  expect(screen.getByText("Stopped.")).toBeInTheDocument();
  expect(screen.queryByTestId("streaming-indicator")).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull(); // not shown as an error
  expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
  expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Copy" })).toBeNull(); // not a finished answer
  expect(rejections).toEqual([]);
});

test("Stop before the first event also ends cleanly, and the next question can be asked", async () => {
  const first = openStream();
  const second = openStream();
  let n = 0;
  routeFetch({ "POST /api/chat/stream": (req) => (n++ === 0 ? first.handler(req) : second.handler(req)) });
  render(<ChatView />);
  ask("one");
  await waitFor(() => expect(first.state.controller).toBeDefined());
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  await flush();
  expect(screen.getByText("Stopped.")).toBeInTheDocument();
  expect(screen.queryByText("Searching your documents…")).toBeNull();
  ask("two");
  await waitFor(() => expect(second.state.controller).toBeDefined());
  expect(second.state.signal!.aborted).toBe(false);
  expect(rejections).toEqual([]);
});

// ---- New chat -------------------------------------------------------------------------------------------

test("New chat is not offered on an empty chat", () => {
  render(<ChatView />);
  expect(screen.queryByRole("button", { name: "New chat" })).toBeNull();
});

test("New chat forgets the stored conversation id, clears the messages and shows the suggested questions again", async () => {
  sessionStorage.setItem(CONVERSATION_STORAGE, ID);
  const f = routeFetch({
    [HISTORY]: () => Response.json([row("user", "q1"), row("assistant", "a1")]),
    "POST /api/chat/stream": () => sse(["token", { text: "fresh" }], done("c2")),
  });
  render(<ChatView />);
  await screen.findByText("a1");
  expect(screen.queryByRole("list", { name: "Suggested questions" })).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  expect(sessionStorage.getItem(CONVERSATION_STORAGE)).toBeNull();
  expect(screen.queryByText("a1")).toBeNull();
  expect(screen.queryByText("q1")).toBeNull();
  expect(screen.queryByRole("button", { name: "New chat" })).toBeNull();
  const suggestions = screen.getByRole("list", { name: "Suggested questions" });
  expect(within(suggestions).getAllByRole("button")).toHaveLength(DEMO_QUERIES.length);

  ask("a new question");
  await screen.findByText("fresh");
  const post = f.calls.find((c) => c.key === "POST /api/chat/stream")!;
  expect(await post.req.json()).toMatchObject({ message: "a new question", conversation_id: null }); // not the old id
  expect(f.keys().filter((k) => k === HISTORY)).toHaveLength(1); // the server history is only read, never touched
  expect(f.keys().some((k) => k.startsWith("DELETE"))).toBe(false);
});

test("New chat during an answer aborts it, and a question asked right after is not disturbed by the old request finishing", async () => {
  const first = openStream();
  const second = openStream();
  let n = 0;
  routeFetch({ "POST /api/chat/stream": (req) => (n++ === 0 ? first.handler(req) : second.handler(req)) });
  render(<ChatView />);
  ask("one");
  await waitFor(() => expect(first.state.controller).toBeDefined());
  first.push("token", { text: "old partial" });
  await screen.findByText("old partial");

  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  expect(first.state.signal!.aborted).toBe(true);
  expect(screen.queryByText("old partial")).toBeNull();
  ask("two");
  await waitFor(() => expect(second.state.controller).toBeDefined());
  await flush(); // the aborted request's cleanup has now run
  expect(screen.getByRole("button", { name: "Stop" })).toBeEnabled(); // still answering "two"
  expect(screen.getByRole("button", { name: "Answering…" })).toBeDisabled();
  second.push("token", { text: "new answer" });
  await screen.findByText("new answer");
  expect(screen.queryByText("old partial")).toBeNull();
  expect(rejections).toEqual([]);
});

// ---- Copy -----------------------------------------------------------------------------------------------

function stubClipboard(writeText: (t: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
}

test("a finished answer has a Copy button that copies its text and says Copied politely", async () => {
  const writeText = vi.fn(async () => {});
  stubClipboard(writeText);
  routeFetch({ "POST /api/chat/stream": () => sse(["token", { text: "Five days ［1］." }], done()) });
  render(<ChatView />);
  ask("refunds?");
  fireEvent.click(await screen.findByRole("button", { name: "Copy" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith("Five days [1].")); // as displayed
  const note = await screen.findByText("Copied");
  expect(note).toHaveAttribute("role", "status");
});

test("a failed copy says so instead of claiming success", async () => {
  stubClipboard(async () => { throw new Error("denied"); });
  routeFetch({ "POST /api/chat/stream": () => sse(["token", { text: "x" }], done()) });
  render(<ChatView />);
  ask("q");
  fireEvent.click(await screen.findByRole("button", { name: "Copy" }));
  expect(await screen.findByText("Could not copy")).toBeInTheDocument();
  expect(screen.queryByText("Copied")).toBeNull();
});

test("Copy is hidden where the clipboard API is unavailable", async () => {
  routeFetch({ "POST /api/chat/stream": () => sse(["token", { text: "answer text" }], done()) });
  render(<ChatView />);
  ask("q");
  await screen.findByText("answer text");
  expect(screen.queryByRole("button", { name: "Copy" })).toBeNull();
});

test("Copy is offered only on finished answers: not while streaming, not on a refusal, not on an error", async () => {
  stubClipboard(async () => {});
  const s = openStream();
  routeFetch({ "POST /api/chat/stream": s.handler });
  const first = render(<ChatView />);
  ask("q");
  await waitFor(() => expect(s.state.controller).toBeDefined());
  s.push("token", { text: "typing" });
  await screen.findByText("typing");
  expect(screen.queryByRole("button", { name: "Copy" })).toBeNull();
  first.unmount();
  sessionStorage.clear();

  routeFetch({ "POST /api/chat/stream": () => sse(["done", { conversation_id: "c1", status: "no_answer", cited: [] }]) });
  const refused = render(<ChatView />);
  ask("q");
  await screen.findByText(/couldn't find anything/);
  expect(screen.queryByRole("button", { name: "Copy" })).toBeNull();
  refused.unmount();
  sessionStorage.clear();

  routeFetch({ "POST /api/chat/stream": () => sse(["error", { code: "llm_timeout" }]) });
  render(<ChatView />);
  ask("q");
  await screen.findByRole("alert");
  expect(screen.queryByRole("button", { name: "Copy" })).toBeNull();
});

// ---- scrolling ------------------------------------------------------------------------------------------

/** Put the end-of-conversation marker `px` below the bottom of an 800 px screen (negative: on screen). */
function markerBelowFold(px: number) {
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ top: 800 + px } as DOMRect);
  window.dispatchEvent(new Event("scroll"));
}

test("after a conversation is restored the latest message is scrolled into view", async () => {
  sessionStorage.setItem(CONVERSATION_STORAGE, ID);
  routeFetch({ [HISTORY]: () => Response.json([row("user", "q1"), row("assistant", "a1")]) });
  render(<ChatView />);
  expect(scrollIntoView).not.toHaveBeenCalled(); // nothing to show while loading
  await screen.findByText("a1");
  await waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({ block: "end" }));
});

test("while streaming the view follows only if the reader is near the bottom", async () => {
  const s = openStream();
  routeFetch({ "POST /api/chat/stream": s.handler });
  render(<ChatView />);
  ask("q");
  await waitFor(() => expect(s.state.controller).toBeDefined());
  s.push("token", { text: "one " });
  await screen.findByText("one");
  await waitFor(() => expect(scrollIntoView).toHaveBeenCalled()); // at the bottom: followed

  markerBelowFold(4000); // the reader scrolled far up
  scrollIntoView.mockClear();
  s.push("token", { text: "two " });
  s.push("token", { text: "three" });
  await screen.findByText(/one two three/);
  expect(scrollIntoView).not.toHaveBeenCalled();
});

test("asking a new question scrolls down even if the reader had scrolled up", async () => {
  routeFetch({ "POST /api/chat/stream": () => sse(["token", { text: "ok" }], done()) });
  render(<ChatView />);
  markerBelowFold(4000);
  scrollIntoView.mockClear();
  ask("q");
  await screen.findByText("ok");
  expect(scrollIntoView).toHaveBeenCalled();
});
