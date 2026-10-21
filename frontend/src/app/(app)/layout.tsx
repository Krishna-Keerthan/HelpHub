import Link from "next/link";
import { LogoutButton } from "@/components/LogoutButton";
import { WakingBanner } from "@/components/WakingBanner";

/** Server-rendered shell only: it never calls the backend. Data loads in client components. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded focus:bg-accent focus:px-3 focus:py-2 focus:text-accent-fg"
      >
        Skip to content
      </a>
      <WakingBanner />
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-line px-4 py-3">
        <span className="font-semibold">HelpHub</span>
        <nav aria-label="Main" className="flex gap-4 text-sm">
          <Link href="/documents">Documents</Link>
          <Link href="/chat">Chat</Link>
          <Link href="/compare">Compare</Link>
        </nav>
        <div className="ml-auto">
          <LogoutButton />
        </div>
      </header>
      <main id="content" tabIndex={-1} className="mx-auto max-w-3xl p-4 focus:outline-none">{children}</main>
    </>
  );
}
