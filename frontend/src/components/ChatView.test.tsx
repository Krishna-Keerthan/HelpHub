import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";
import { routeFetch, sse } from "@/test/fetch-mock";
import { ChatView } from "./ChatView";

const source = (index: number, title: string) => ({
  index,
  chunk_id: `c${index}`,
  document_id: `d${index}`,
  document_title: title,
  chunk_index: 0,
  score: 0.8,
});

function ask(text: string) {
  fireEvent.change(screen.getByLabelText("Your question"), { target: { value: text } });
  fireEvent.submit(screen.getByRole("form", { name: "Ask a question" }));
}

test("streams tokens and shows only the cited sources", async () => {
  routeFetch({
    "POST /api/chat/stream": () =>
      sse(
        ["sources", { conversation_id: "c1", sources: [source(1, "Refund policy"), source(2, "Other doc")] }],
        ["token", { text: "Refunds take " }],
        ["token", { text: "5 days [1]." }],
        ["done", { conversation_id: "c1", status: "complete", cited: [1] }],
      ),
  });
  render(<ChatView />);
  ask("How long do refunds take?");
  expect(await screen.findByText("Refunds take 5 days [1].")).toBeInTheDocument();
  const sources = await screen.findByRole("list", { name: "Sources" });
  expect(sources).toHaveTextContent("[1] Refund policy");
  expect(sources).not.toHaveTextContent("Other doc");
});

test("refusal is detected by done.status, not by text", async () => {
  routeFetch({
    "POST /api/chat/stream": () =>
      sse(
        ["sources", { conversation_id: "c1", sources: [] }],
        ["token", { text: "some backend wording" }],
        ["done", { conversation_id: "c1", status: "no_answer", cited: [] }],
      ),
  });
  render(<ChatView />);
  ask("What is the moon made of?");
  expect(await screen.findByText(/couldn't find anything in your documents/)).toBeInTheDocument();
  expect(screen.queryByText("some backend wording")).not.toBeInTheDocument();
  expect(screen.queryByRole("list", { name: "Sources" })).not.toBeInTheDocument();
});

test("embedding_unavailable error event is explained", async () => {
  routeFetch({
    "POST /api/chat/stream": () =>
      sse(["error", { conversation_id: "c1", code: "embedding_unavailable" }]),
  });
  render(<ChatView />);
  ask("hello");
  expect(await screen.findByRole("alert")).toHaveTextContent("Search is temporarily unavailable");
});

test("keeps partial text and shows the error when the stream fails mid-answer", async () => {
  routeFetch({
    "POST /api/chat/stream": () =>
      sse(
        ["sources", { conversation_id: "c1", sources: [source(1, "A")] }],
        ["token", { text: "Partial" }],
        ["error", { conversation_id: "c1", code: "llm_timeout" }],
      ),
  });
  render(<ChatView />);
  ask("hello");
  expect(await screen.findByRole("alert")).toHaveTextContent("took too long");
  expect(screen.getByText("Partial")).toBeInTheDocument();
});

test("429 shows Retry-After seconds", async () => {
  routeFetch({
    "POST /api/chat/stream": () =>
      Response.json({ detail: "x" }, { status: 429, headers: { "Retry-After": "12" } }),
  });
  render(<ChatView />);
  ask("hello");
  expect(await screen.findByRole("alert")).toHaveTextContent("Try again in 12 seconds");
});

test("cold start (503) shows the waking message", async () => {
  routeFetch({ "POST /api/chat/stream": () => Response.json({ code: "service_waking" }, { status: 503 }) });
  render(<ChatView />);
  ask("hello");
  expect(await screen.findByRole("alert")).toHaveTextContent("waking up");
});

test("a stream that ends without done is reported, and the conversation id is reused", async () => {
  const bodies: unknown[] = [];
  let n = 0;
  const f = routeFetch({
    "POST /api/chat/stream": async (req) => {
      bodies.push(await req.json());
      return n++ === 0
        ? sse(["sources", { conversation_id: "c9", sources: [] }], ["token", { text: "cut" }])
        : sse(["done", { conversation_id: "c9", status: "complete", cited: [] }]);
    },
  });
  render(<ChatView />);
  ask("one");
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
  await waitFor(() => expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled());
  ask("two");
  await waitFor(() => expect(f.calls).toHaveLength(2));
  expect(bodies[1]).toMatchObject({ conversation_id: "c9", message: "two" });
});

test("answers are a polite live region marked busy only while streaming", async () => {
  routeFetch({
    "POST /api/chat/stream": () =>
      sse(["token", { text: "Hi" }], ["done", { conversation_id: "c1", status: "complete", cited: [] }]),
  });
  render(<ChatView />);
  expect(screen.getByRole("list", { name: "Conversation" })).toBeInTheDocument();
  ask("hello");
  const answer = (await screen.findByText("Hi")).parentElement as HTMLElement;
  expect(answer).toHaveAttribute("aria-live", "polite");
  await waitFor(() => expect(answer).toHaveAttribute("aria-busy", "false"));
});

test("focus returns to the input only when it was in the form; it is never stolen", async () => {
  routeFetch({
    "POST /api/chat/stream": () => sse(["done", { conversation_id: "c1", status: "complete", cited: [] }]),
  });
  render(<div><a href="#x">elsewhere</a><ChatView /></div>);
  const input = screen.getByLabelText("Your question");
  const other = screen.getByRole("link", { name: "elsewhere" });

  other.focus();
  ask("one");
  await waitFor(() => expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled());
  await new Promise((r) => setTimeout(r, 10));
  expect(other).toHaveFocus();

  input.focus();
  ask("two");
  await waitFor(() => expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled());
  await waitFor(() => expect(input).toHaveFocus());
});

test("the searching state is an informational polite status, errors stay alerts", async () => {
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  routeFetch({
    "POST /api/chat/stream": async () => {
      await gate;
      return sse(["error", { conversation_id: "c1", code: "llm_timeout" }]);
    },
  });
  render(<ChatView />);
  ask("hello");
  expect(await screen.findByRole("status")).toHaveTextContent("Searching");
  release();
  expect(await screen.findByRole("alert")).toHaveTextContent("took too long");
});

test("empty state invites a first question and disappears after asking", async () => {
  routeFetch({
    "POST /api/chat/stream": () => sse(["done", { conversation_id: "c1", status: "complete", cited: [] }]),
  });
  render(<ChatView />);
  expect(screen.getByText(/Ask a question about your documents/)).toBeInTheDocument();
  ask("hello");
  await waitFor(() => expect(screen.queryByText(/Ask a question about your documents/)).not.toBeInTheDocument());
});

test("lenticular markers show as [n] in the answer; chips still follow done.cited", async () => {
  routeFetch({
    "POST /api/chat/stream": () =>
      sse(
        ["sources", { conversation_id: "c1", sources: [source(1, "Refund policy"), source(2, "Storage quotas")] }],
        ["token", { text: "Free up space" }],
        ["token", { text: "【2】." }],
        ["done", { conversation_id: "c1", status: "complete", cited: [2] }],
      ),
  });
  render(<ChatView />);
  ask("What if uploads fail?");
  expect(await screen.findByText("Free up space[2].")).toBeInTheDocument();
  const sources = await screen.findByRole("list", { name: "Sources" });
  expect(sources).toHaveTextContent("[2] Storage quotas");
  expect(sources).not.toHaveTextContent("Refund policy");
});

test("a marker for a source that is not in done.cited adds no chip", async () => {
  routeFetch({
    "POST /api/chat/stream": () =>
      sse(
        ["sources", { conversation_id: "c1", sources: [source(1, "Refund policy")] }],
        ["token", { text: "Five days［1］." }],
        ["done", { conversation_id: "c1", status: "complete", cited: [] }],
      ),
  });
  render(<ChatView />);
  ask("q");
  expect(await screen.findByText("Five days[1].")).toBeInTheDocument();
  expect(screen.queryByRole("list", { name: "Sources" })).toBeNull();
});
