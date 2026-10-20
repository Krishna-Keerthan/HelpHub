import Link from "next/link";
import { LogoutButton } from "@/components/LogoutButton";
import { WakingBanner } from "@/components/WakingBanner";

/** Server-rendered shell only: it never calls the backend. Data loads in client components. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <WakingBanner />
      <header className="flex items-center gap-6 border-b border-zinc-200 px-4 py-3">
        <span className="font-semibold">HelpHub</span>
        <nav className="flex gap-4 text-sm">
          <Link href="/documents">Documents</Link>
          <Link href="/chat">Chat</Link>
        </nav>
        <div className="ml-auto">
          <LogoutButton />
        </div>
      </header>
      <main className="mx-auto max-w-3xl p-4">{children}</main>
    </>
  );
}
