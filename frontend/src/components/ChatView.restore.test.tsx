import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { STREAM_CUT_OFF_MESSAGE } from "@/lib/ui/chat-state";
import { CONVERSATION_STORAGE } from "@/lib/session/storage";
import { render } from "@/test/render";
import { routeFetch, sse } from "@/test/fetch-mock";
import { ChatView } from "./ChatView";

const ID = "11111111-1111-1111-1111-111111111111";
const HISTORY = `GET /api/conversations/${ID}/messages`;
const src = (index: number, title: string) => ({
  index, chunk_id: `c${index}`, document_id: `d${index}`, document_title: title, chunk_index: 0, score: 0.8,
});
const row = (role: string, content: string, status = "complete", sources: unknown[] = []) => ({
  id: `m-${content}`, role, content, status, sources, model: null, created_at: "2026-01-01T00:00:00Z",
});

function ask(text: string) {
  fireEvent.change(screen.getByLabelText("Your question"), { target: { value: text } });
  fireEvent.submit(screen.getByRole("form", { name: "Ask a question" }));
}

test("a stored id fetches the history once, shows the loading notice, then the turns", async () => {
  sessionStorage.setItem(CONVERSATION_STORAGE, ID);
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  const f = routeFetch({
    [HISTORY]: async () => {
      await gate;
      return Response.json([
        row("user", "How long do refunds take?"),
        row("assistant", "Five days [2].", "complete", [src(1, "Intro"), src(2, "Refund policy")]),
      ]);
    },
  });
  render(<ChatView />);
  expect(await screen.findByText("Loading conversation…")).toBeInTheDocument();
  expect(screen.getByLabelText("Your question")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
  release();
  expect(await screen.findByText("How long do refunds take?")).toBeInTheDocument();
  expect(screen.getByText("Five days [2].")).toBeInTheDocument();
  expect(screen.queryByText("Loading conversation…")).not.toBeInTheDocument();
  expect(screen.getByRole("list", { name: "Sources" })).toHaveTextContent("[2] Refund policy");
  expect(screen.getByRole("list", { name: "Sources" })).not.toHaveTextContent("Intro");
  expect(screen.getByLabelText("Your question")).toBeEnabled();
  expect(f.keys()).toEqual([HISTORY]);
  expect(new URL(f.calls[0]!.req.url).searchParams.get("limit")).toBe("200");
});

test("the restored chat continues the same conversation with the next turn id", async () => {
  sessionStorage.setItem(CONVERSATION_STORAGE, ID);
  const bodies: unknown[] = [];
  routeFetch({
    [HISTORY]: () => Response.json([row("user", "q1"), row("assistant", "a1")]),
    "POST /api/chat/stream": async (req) => {
      bodies.push(await req.json());
      return sse(["token", { text: "a2" }], ["done", { conversation_id: ID, status: "complete", cited: [] }]);
    },
  });
  render(<ChatView />);
  await screen.findByText("a1");
  ask("q2");
  await screen.findByText("a2");
  expect(bodies[0]).toMatchObject({ conversation_id: ID, message: "q2" });
  expect(screen.getByText("q1")).toBeInTheDocument();
  expect(screen.getAllByRole("listitem").filter((li) => li.textContent?.startsWith("q"))).toHaveLength(2);
});

test("a 404 clears the stored id and shows the normal empty state", async () => {
  sessionStorage.setItem(CONVERSATION_STORAGE, ID);
  routeFetch({ [HISTORY]: () => Response.json({ detail: "Conversation not found" }, { status: 404 }) });
  render(<ChatView />);
  expect(await screen.findByText(/Ask a question about your documents/)).toBeInTheDocument();
  expect(sessionStorage.getItem(CONVERSATION_STORAGE)).toBeNull();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Your question")).toBeEnabled();
});

test("another history error shows the failure, keeps the id, and re-enables the input and Ask", async () => {
  sessionStorage.setItem(CONVERSATION_STORAGE, ID);
  const bodies: unknown[] = [];
  routeFetch({
    [HISTORY]: () => Response.json({ detail: "x" }, { status: 500 }),
    "POST /api/chat/stream": async (req) => {
      bodies.push(await req.json());
      return sse(["done", { conversation_id: ID, status: "complete", cited: [] }]);
    },
  });
  render(<ChatView />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
  expect(sessionStorage.getItem(CONVERSATION_STORAGE)).toBe(ID);
  expect(screen.getByLabelText("Your question")).toBeEnabled();
  expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  ask("still works");
  await waitFor(() => expect(bodies).toHaveLength(1));
  expect(bodies[0]).toMatchObject({ conversation_id: ID });
});

test("an orphan user message shows the cut-off state, and a new question afterwards works", async () => {
  sessionStorage.setItem(CONVERSATION_STORAGE, ID);
  routeFetch({
    [HISTORY]: () => Response.json([row("user", "left mid-answer")]),
    "POST /api/chat/stream": () =>
      sse(["token", { text: "fresh answer" }], ["done", { conversation_id: ID, status: "complete", cited: [] }]),
  });
  render(<ChatView />);
  expect(await screen.findByText("left mid-answer")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent(STREAM_CUT_OFF_MESSAGE);
  ask("again");
  expect(await screen.findByText("fresh answer")).toBeInTheDocument();
  expect(screen.getByText("left mid-answer")).toBeInTheDocument();
});

test("with no stored id no request is made", async () => {
  const f = routeFetch({});
  render(<ChatView />);
  await new Promise((r) => setTimeout(r, 20));
  expect(f.calls).toHaveLength(0);
  expect(screen.getByText(/Ask a question about your documents/)).toBeInTheDocument();
  expect(screen.queryByText("Loading conversation…")).not.toBeInTheDocument();
});

test("sending a message stores the conversation id from the stream", async () => {
  routeFetch({
    "POST /api/chat/stream": () =>
      sse(["sources", { conversation_id: ID, sources: [] }], ["done", { conversation_id: ID, status: "no_answer", cited: [] }]),
  });
  render(<ChatView />);
  ask("hello");
  await waitFor(() => expect(sessionStorage.getItem(CONVERSATION_STORAGE)).toBe(ID));
});

test("a 404 on send clears the stored id", async () => {
  sessionStorage.setItem(CONVERSATION_STORAGE, ID);
  routeFetch({
    [HISTORY]: () => Response.json([]),
    "POST /api/chat/stream": () => Response.json({ detail: "x" }, { status: 404 }),
  });
  render(<ChatView />);
  await waitFor(() => expect(screen.getByLabelText("Your question")).toBeEnabled());
  ask("hello");
  await screen.findByRole("alert");
  expect(sessionStorage.getItem(CONVERSATION_STORAGE)).toBeNull();
});

test("blocked storage does not break chat", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  routeFetch({
    "POST /api/chat/stream": () =>
      sse(["token", { text: "works" }], ["done", { conversation_id: ID, status: "complete", cited: [] }]),
  });
  render(<ChatView />);
  expect(screen.getByLabelText("Your question")).toBeEnabled();
  ask("hello");
  expect(await screen.findByText("works")).toBeInTheDocument();
  vi.restoreAllMocks();
});

test("an invalid stored source in the middle is dropped and the right chips are cited", async () => {
  sessionStorage.setItem(CONVERSATION_STORAGE, ID);
  routeFetch({
    [HISTORY]: () =>
      Response.json([
        row("user", "q"),
        row("assistant", "See [1] and [3].", "complete", [src(1, "First doc"), { index: 2, title: "malformed" }, src(3, "Third doc")]),
      ]),
  });
  render(<ChatView />);
  await screen.findByText("See [1] and [3].");
  const chips = screen.getByRole("list", { name: "Sources" });
  expect(chips).toHaveTextContent("[1] First doc");
  expect(chips).toHaveTextContent("[3] Third doc");
  expect(chips).not.toHaveTextContent("[2]");
  expect(chips.querySelectorAll("li")).toHaveLength(2);
});
