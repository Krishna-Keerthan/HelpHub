import type { Metadata } from "next";
import { UsersView } from "@/components/UsersView";

export const metadata: Metadata = {
  title: "Users",
  description: "List and add the people who can sign in to this workspace.",
};

export default function UsersPage() {
  return <UsersView />;
}
