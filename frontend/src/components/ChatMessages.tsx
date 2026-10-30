import type { Turn } from "@/lib/ui/chat-state";
import { ChatMessage } from "./ChatMessage";

export function ChatMessages({ turns }: { turns: Turn[] }) {
  return (
    <ol aria-label="Conversation">
      {turns.map((t) => (
        <ChatMessage key={t.id} turn={t} />
      ))}
    </ol>
  );
}
