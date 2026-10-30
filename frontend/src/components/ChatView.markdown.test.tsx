import { fireEvent, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { render } from "@/test/render";
import { routeFetch, sse } from "@/test/fetch-mock";
import { ChatView } from "./ChatView";

function ask(text: string) {
  fireEvent.change(screen.getByLabelText("Your question"), { target: { value: text } });
  fireEvent.submit(screen.getByRole("form", { name: "Ask a question" }));
}

const ANSWER = "Options:\n\n* **Card** refunds [1]\n* Cash refunds [4]\n";

test("a streamed answer renders bullets and bold, keeps [n], and the user's own message stays plain text", async () => {
  routeFetch({
    "POST /api/chat/stream": () =>
      sse(
        ["token", { text: ANSWER.slice(0, 20) }],
        ["token", { text: ANSWER.slice(20) }],
        ["done", { conversation_id: "c1", status: "complete", cited: [] }],
      ),
  });
  const { container } = render(<ChatView />);
  ask("what about **my** refund?");
  await screen.findByText("Cash refunds [4]");
  const items = screen.getAllByRole("listitem");
  const bullets = items.filter((i) => !i.querySelector("li")); // leaf items; the turn itself is also an <li>
  expect(bullets.map((i) => i.textContent)).toEqual(["Card refunds [1]", "Cash refunds [4]"]);
  expect(container.querySelector("strong")).toHaveTextContent("Card");
  // The question is not Markdown: its asterisks are still there and nothing in it is bold.
  expect(screen.getByText("what about **my** refund?")).toBeInTheDocument();
  expect(container.querySelectorAll("strong")).toHaveLength(1);
});
