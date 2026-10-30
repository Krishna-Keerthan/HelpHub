import Link from "next/link";
import { RequestAccessLink } from "@/components/RequestAccessLink";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { BrandLink } from "@/components/shell/BrandLink";
import { StickyHeader } from "@/components/shell/StickyHeader";
import { buttonClass } from "@/components/ui/styles";

const ANCHOR = "inline-flex min-h-10 items-center rounded-md px-3 text-sm font-medium text-muted motion-safe:transition-colors hover:bg-chip hover:text-fg";

/** The home page's top bar (the shared sticky header). The two anchors are hidden on phones; the theme toggle and Sign in always stay. */
export function HomeNav({ contactEmail, signedIn = false }: { contactEmail: string | undefined; signedIn?: boolean }) {
  return (
    <StickyHeader innerClass="max-w-5xl">
        <BrandLink href="/home" className="mr-auto" />
        <nav aria-label="Page sections" className="hidden items-center gap-1 sm:flex">
          <a href="#features" className={ANCHOR}>Features</a>
          <a href="#faq" className={ANCHOR}>FAQ</a>
        </nav>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          {signedIn ? (
            <Link href="/documents" className={buttonClass({ variant: "primary" })}>Open the app</Link>
          ) : (
            <>
              <Link href="/login" className={buttonClass({ variant: "ghost" })}>Sign in</Link>
              <RequestAccessLink contactEmail={contactEmail} />
            </>
          )}
        </div>
    </StickyHeader>
  );
}
