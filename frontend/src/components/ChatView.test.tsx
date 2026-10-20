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
