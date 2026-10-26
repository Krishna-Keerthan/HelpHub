import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { DEMO_QUERIES } from "@/lib/demo-queries";
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
  expect(await screen.findByRole("alert")).toHaveTextContent("The search service is unavailable. Please try again later.");
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
  expect(await screen.findByRole("alert")).toHaveTextContent("Wait 12 seconds and ask again");
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
  expect(await screen.findByRole("status")).toHaveTextContent("Searching your documents…");
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

test("first visit lists the five demo questions; clicking one asks it and the list goes away", async () => {
  const bodies: unknown[] = [];
  routeFetch({
    "POST /api/chat/stream": async (req) => {
      bodies.push(await req.json());
      return sse(["token", { text: "ok" }], ["done", { conversation_id: "c1", status: "complete", cited: [] }]);
    },
  });
  render(<ChatView />);
  expect(screen.getByText(/searches them and answers with citations/)).toBeInTheDocument();
  const list = screen.getByRole("list", { name: "Suggested questions" });
  expect(DEMO_QUERIES).toHaveLength(5);
  expect(within(list).getAllByRole("button").map((b) => b.textContent)).toEqual([...DEMO_QUERIES]);

  fireEvent.click(within(list).getByRole("button", { name: DEMO_QUERIES[1]! }));
  expect(await screen.findByText("ok")).toBeInTheDocument();
  expect(bodies).toEqual([{ message: DEMO_QUERIES[1], conversation_id: null }]);
  expect(screen.queryByRole("list", { name: "Suggested questions" })).toBeNull();
  expect(screen.getByRole("list", { name: "Conversation" })).toHaveTextContent(DEMO_QUERIES[1]!);
});

/** An SSE response that stays open after `first` until `rest()` is called. */
function heldStream(first: [string, object][]) {
  const enc = new TextEncoder();
  const msg = ([e, d]: [string, object]) => enc.encode(`event: ${e}\ndata: ${JSON.stringify(d)}\n\n`);
  let ctl!: ReadableStreamDefaultController<Uint8Array>;
  const res = () =>
    new Response(new ReadableStream<Uint8Array>({ start: (c) => { ctl = c; first.forEach((e) => c.enqueue(msg(e))); } }), {
      headers: { "Content-Type": "text/event-stream" },
    });
  return { res, rest: (events: [string, object][]) => { events.forEach((e) => ctl.enqueue(msg(e))); ctl.close(); } };
}

const docRow = (id: string, title: string) => ({
  id, title, status: "READY", error: null, created_by: null,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
});

const answerWithSource = () =>
  sse(
    ["sources", { conversation_id: "c1", sources: [source(1, "Stale title")] }],
    ["token", { text: "Five days [1]." }],
    ["done", { conversation_id: "c1", status: "complete", cited: [1] }],
  );

test("a citation chip is a button; opening it resolves the title from the documents list and says the passage is not available", async () => {
  const f = routeFetch({
    "POST /api/chat/stream": answerWithSource,
    "GET /api/documents": () => Response.json([docRow("d1", "Refund policy v2")]),
  });
  render(<ChatView />);
  ask("refunds?");
  const chip = await screen.findByRole("button", { name: /\[1\] Stale title/ });
  expect(chip).toHaveAttribute("aria-expanded", "false");
  expect(f.keys()).not.toContain("GET /api/documents"); // nothing is fetched until a chip is used

  fireEvent.click(chip);
  expect(await screen.findByRole("button", { name: /\[1\] Refund policy v2/ })).toHaveAttribute("aria-expanded", "true");
  const panel = screen.getByRole("region", { name: "Source 1" });
  expect(panel).toHaveTextContent("Refund policy v2");
  expect(panel).not.toHaveTextContent(/section/i);
  expect(panel).toHaveTextContent("does not include the cited passage");
  expect(within(panel).getByRole("link", { name: "Open the documents list" })).toHaveAttribute("href", "/documents");

  fireEvent.click(screen.getByRole("button", { name: /\[1\]/ }));
  expect(screen.queryByRole("region", { name: "Source 1" })).toBeNull();
  expect(f.keys().filter((k) => k === "GET /api/documents")).toHaveLength(1);
});

test("a cited document that is no longer listed keeps its title and says so; a failed list falls back to the cited title", async () => {
  routeFetch({
    "POST /api/chat/stream": answerWithSource,
    "GET /api/documents": () => Response.json([docRow("other", "Something else")]),
  });
  const first = render(<ChatView />);
  ask("q");
  fireEvent.click(await screen.findByRole("button", { name: /\[1\] Stale title/ }));
  expect(await screen.findByText(/no longer in your library/)).toBeInTheDocument();
  first.unmount();

  routeFetch({
    "POST /api/chat/stream": answerWithSource,
    "GET /api/documents": () => Response.json({ detail: "x" }, { status: 500 }),
  });
  render(<ChatView />);
  ask("q");
  fireEvent.click(await screen.findByRole("button", { name: /\[1\] Stale title/ }));
  const panel = await screen.findByRole("region", { name: "Source 1" });
  expect(panel).toHaveTextContent("Stale title");
  expect(panel).not.toHaveTextContent("no longer in your library");
});

test("waiting states: searching, then cold-start message when the first event is slow, then writing, then a streaming indicator until done", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  try {
    let release!: (r: Response) => void;
    const gate = new Promise<Response>((r) => (release = r));
    routeFetch({ "POST /api/chat/stream": () => gate });
    render(<ChatView />);
    ask("hello");
    expect(screen.getByRole("status")).toHaveTextContent("Searching your documents…");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7000);
    });
    expect(screen.getByRole("status")).toHaveTextContent("Searching your documents…");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(screen.getByRole("status")).toHaveTextContent("Waking the server, this can take about a minute");
    expect(screen.queryByRole("alert")).toBeNull();

    const held = heldStream([
      ["sources", { conversation_id: "c1", sources: [source(1, "A"), source(2, "B")] }],
      ["token", { text: "Hi" }],
    ]);
    release(held.res());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(screen.getByTestId("streaming-indicator")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
    held.rest([["done", { conversation_id: "c1", status: "complete", cited: [] }]]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(screen.queryByTestId("streaming-indicator")).toBeNull();
  } finally {
    vi.useRealTimers();
  }
});

test("between sources and the first token the status says the answer is being written", async () => {
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  routeFetch({
    "POST /api/chat/stream": () => {
      const enc = new TextEncoder();
      return new Response(
        new ReadableStream({
          async start(c) {
            c.enqueue(enc.encode(`event: sources\ndata: ${JSON.stringify({ conversation_id: "c1", sources: [source(1, "A")] })}\n\n`));
            await gate;
            c.enqueue(enc.encode(`event: done\ndata: ${JSON.stringify({ conversation_id: "c1", status: "complete", cited: [] })}\n\n`));
            c.close();
          },
        }),
        { headers: { "Content-Type": "text/event-stream" } },
      );
    },
  });
  render(<ChatView />);
  ask("hello");
  expect(await screen.findByText(/Found 1 matching passage\. Writing the answer…/)).toBeInTheDocument();
  release();
  await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
});

test("a lost connection is explained, and a 404 on a stale conversation starts a new one next time", async () => {
  const bodies: unknown[] = [];
  let n = 0;
  routeFetch({
    "POST /api/chat/stream": async (req) => {
      bodies.push(await req.json());
      n++;
      if (n === 1) return sse(["sources", { conversation_id: "c7", sources: [] }], ["done", { conversation_id: "c7", status: "complete", cited: [] }]);
      if (n === 2) return Response.json({ detail: "Conversation not found" }, { status: 404 });
      return sse(["done", { conversation_id: "c8", status: "complete", cited: [] }]);
    },
  });
  render(<ChatView />);
  ask("one");
  await waitFor(() => expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled());
  ask("two");
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("conversation is no longer available");
  expect(alert).not.toHaveTextContent("Conversation not found");
  await waitFor(() => expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled());
  ask("three");
  await waitFor(() => expect(bodies).toHaveLength(3));
  expect(bodies[1]).toMatchObject({ conversation_id: "c7" });
  expect(bodies[2]).toMatchObject({ conversation_id: null });
});

test("a network failure before any answer says the server could not be reached", async () => {
  routeFetch({
    "POST /api/chat/stream": () => {
      throw new TypeError("Failed to fetch");
    },
  });
  render(<ChatView />);
  ask("hello");
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Could not reach the server");
  expect(alert).not.toHaveTextContent("Failed to fetch");
});
