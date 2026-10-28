import Link from "next/link";
import { RequestAccessLink } from "@/components/RequestAccessLink";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { buttonClass } from "@/components/ui/styles";

const ANCHOR = "inline-flex min-h-10 items-center rounded-md px-3 text-sm font-medium text-muted motion-safe:transition-colors hover:bg-chip hover:text-fg";

/** Sticky top bar. The two anchors are hidden on phones; the theme toggle and Sign in always stay. */
export function HomeNav({ contactEmail }: { contactEmail: string | undefined }) {
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-surface/90 backdrop-blur">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2">
        <span className="mr-auto font-semibold tracking-tight">HelpHub</span>
        <nav aria-label="Page sections" className="hidden items-center gap-1 sm:flex">
          <a href="#features" className={ANCHOR}>Features</a>
          <a href="#faq" className={ANCHOR}>FAQ</a>
        </nav>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <Link href="/login" className={buttonClass({ variant: "ghost" })}>Sign in</Link>
          <RequestAccessLink contactEmail={contactEmail} />
        </div>
      </div>
    </header>
  );
}
