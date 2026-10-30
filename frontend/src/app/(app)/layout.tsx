import { NavLink } from "@/components/ui/NavLink";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { AccountChip } from "@/components/AccountChip";
import { BrandLink } from "@/components/shell/BrandLink";
import { SiteFooter } from "@/components/shell/SiteFooter";
import { SkipLink } from "@/components/shell/SkipLink";
import { StickyHeader } from "@/components/shell/StickyHeader";
import { LogoutButton } from "@/components/LogoutButton";
import { UsersNavLink } from "@/components/UsersNavLink";

/** Server-rendered shell only: it never calls the backend. Data loads in client components. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SkipLink />
      {/* Named group: the header's inner width follows main (max-w-3xl, or 5xl when a page has [data-wide]). */}
      <div className="group/shell flex min-h-screen flex-col">
      {/* Two rows at every width: brand on the left of row one with the account chip, theme toggle and Log out on
          the right, the nav on row two. DOM order is brand, nav, actions (the tab order); `order` places the actions
          beside the brand. No overflow, so focus rings are never clipped. */}
      <StickyHeader innerClass="max-w-3xl group-has-[[data-wide]]/shell:max-w-5xl sm:gap-x-4">
          <BrandLink href="/documents" className="order-1" />
          <nav aria-label="Main" className="order-3 flex basis-full flex-wrap gap-1">
            <NavLink href="/home">Home</NavLink>
            <NavLink href="/documents">Documents</NavLink>
            <NavLink href="/chat">Chat</NavLink>
            <NavLink href="/compare">Compare</NavLink>
            <UsersNavLink />
          </nav>
          <div className="order-2 ml-auto flex min-w-0 items-center gap-1 sm:gap-2">
            <AccountChip />
            <ThemeToggle />
            <LogoutButton />
          </div>
      </StickyHeader>
      <main id="content" tabIndex={-1} className="mx-auto w-full max-w-3xl flex-1 p-4 sm:py-6 focus:outline-none has-[[data-wide]]:max-w-5xl">{children}</main>
      {/* Same container rule as the header and main, so the footer lines up with the page. */}
      <SiteFooter containerClass="max-w-3xl group-has-[[data-wide]]/shell:max-w-5xl" />
      </div>
    </>
  );
}
