import Link from "next/link";
import { NavLink } from "@/components/ui/NavLink";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { AccountChip } from "@/components/AccountChip";
import { HomeFooter } from "@/components/home/HomeFooter";
import { LogoutButton } from "@/components/LogoutButton";
import { UsersNavLink } from "@/components/UsersNavLink";
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
      {/* Named group: the header's inner width follows main (max-w-3xl, or 5xl when a page has [data-wide]). */}
      <div className="group/shell flex min-h-screen flex-col">
      <WakingBanner />
      <header className="border-b border-line bg-surface-raised">
        {/* Phone: brand and Log out on row one, the nav wraps below. sm and up: one row. No overflow, so focus rings are never clipped. */}
        <div className="mx-auto flex max-w-3xl flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2 group-has-[[data-wide]]/shell:max-w-5xl sm:gap-x-4">
          <Link href="/documents" className="order-1 shrink-0 rounded-md font-semibold tracking-tight">HelpHub</Link>
          <nav aria-label="Main" className="order-3 flex basis-full flex-wrap gap-1 sm:order-2 sm:basis-auto sm:flex-1">
            <NavLink href="/home">Home</NavLink>
            <NavLink href="/documents">Documents</NavLink>
            <NavLink href="/chat">Chat</NavLink>
            <NavLink href="/compare">Compare</NavLink>
            <UsersNavLink />
          </nav>
          <AccountChip />
          <div className="order-2 ml-auto flex shrink-0 items-center gap-1 sm:order-4 sm:ml-0">
            <ThemeToggle />
            <LogoutButton />
          </div>
        </div>
      </header>
      <main id="content" tabIndex={-1} className="mx-auto w-full max-w-3xl flex-1 p-4 sm:py-6 focus:outline-none has-[[data-wide]]:max-w-5xl">{children}</main>
      {/* Same container rule as the header and main, so the footer lines up with the page. */}
      <div className="mx-auto w-full max-w-3xl px-4 group-has-[[data-wide]]/shell:max-w-5xl">
        <HomeFooter contactEmail={process.env.NEXT_PUBLIC_CONTACT_EMAIL} showHome />
      </div>
      </div>
    </>
  );
}
