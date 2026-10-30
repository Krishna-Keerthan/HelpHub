import type { Metadata } from "next";
import { ChatView } from "@/components/ChatView";

export const metadata: Metadata = {
  title: "Chat",
  description: "Ask a question and get an answer that cites your documents.",
};

export default function ChatPage() {
  return <ChatView />;
}
