import { NavLink } from "@/components/ui/NavLink";
import { LogoutButton } from "@/components/LogoutButton";
import { WakingBanner } from "@/components/WakingBanner";

/** Server-rendered shell only: it never calls the backend. Data loads in client components. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-accent-fg"
      >
        Skip to content
      </a>
      <WakingBanner />
      <header className="border-b border-line bg-surface-raised">
        <div className="mx-auto flex max-w-5xl items-center gap-x-2 px-4 py-2 sm:gap-x-4">
          <span className="shrink-0 font-semibold tracking-tight">HelpHub</span>
          <nav aria-label="Main" className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
            <NavLink href="/documents">Documents</NavLink>
            <NavLink href="/chat">Chat</NavLink>
            <NavLink href="/compare">Compare</NavLink>
          </nav>
          <div className="shrink-0">
            <LogoutButton />
          </div>
        </div>
      </header>
      <main id="content" tabIndex={-1} className="mx-auto max-w-3xl p-4 sm:py-6 focus:outline-none has-[[data-wide]]:max-w-5xl">{children}</main>
    </>
  );
}
