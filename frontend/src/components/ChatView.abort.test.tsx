import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { render } from "@/test/render";
import { ChatView } from "./ChatView";

const abortError = () => new DOMException("The user aborted a request.", "AbortError");

let rejections: unknown[] = [];
const onRejection = (reason: unknown) => void rejections.push(reason);
const onWindowRejection = (e: PromiseRejectionEvent) => void rejections.push(e.reason);

beforeEach(() => {
  rejections = [];
  process.on("unhandledRejection", onRejection);
  window.addEventListener("unhandledrejection", onWindowRejection);
});
afterEach(() => {
  process.off("unhandledRejection", onRejection);
  window.removeEventListener("unhandledrejection", onWindowRejection);
});

/** A fetch that honours the request's signal like a browser does: it rejects before headers, errors the body after. */
function abortableFetch(mode: "mid-stream" | "before-headers") {
  const started = vi.fn();
  vi.stubGlobal(
    "fetch",
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : new Request(String(input), init);
      started();
      if (mode === "before-headers") {
        return new Promise<Response>((_, reject) => {
          req.signal.addEventListener("abort", () => reject(abortError()));
        });
      }
      const enc = new TextEncoder();
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(
            enc.encode(`event: sources\ndata: ${JSON.stringify({ conversation_id: "c1", sources: [] })}\n\n`),
          );
          req.signal.addEventListener("abort", () => controller.error(abortError()));
        },
      });
      return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
    },
  );
  return started;
}

const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 30)); });

async function leaveWhileStreaming(mode: "mid-stream" | "before-headers") {
  const started = abortableFetch(mode);
  const view = render(<ChatView />);
  fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "hello" } });
  fireEvent.submit(screen.getByRole("form", { name: "Ask a question" }));
  await waitFor(() => expect(started).toHaveBeenCalled());
  await flush();
  view.unmount();
  await flush();
}

test("leaving the page while an answer is streaming produces no unhandled rejection", async () => {
  await leaveWhileStreaming("mid-stream");
  expect(rejections).toEqual([]);
});

test("leaving the page before the answer starts produces no unhandled rejection", async () => {
  await leaveWhileStreaming("before-headers");
  expect(rejections).toEqual([]);
});
