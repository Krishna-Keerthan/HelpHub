import Link from "next/link";
import { LogoutButton } from "@/components/LogoutButton";
import { WakingBanner } from "@/components/WakingBanner";

/** Server-rendered shell only: it never calls the backend. Data loads in client components. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <WakingBanner />
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-line px-4 py-3">
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
