import Link from "next/link";
import { contactHref } from "@/lib/request-access";
import { captionClass } from "@/components/ui/styles";

const LINK = "rounded-md text-sm text-muted underline-offset-4 hover:text-fg hover:underline";

/**
 * The one footer, used by every page. It sits after `<main>` (never inside it) in a column whose `main` grows, so
 * on a short page it ends at the bottom of the screen. `containerClass` carries the width rule of that page's
 * header, so the two line up.
 */
export function SiteFooter({ containerClass }: { containerClass: string }) {
  const contact = contactHref(process.env.NEXT_PUBLIC_CONTACT_EMAIL);
  return (
    <div className={`mx-auto w-full px-4 ${containerClass}`}>
      <footer className="mt-8 border-t border-line py-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <p className="flex items-center gap-2 font-medium">
            <span aria-hidden="true" className="h-4 w-1 rounded-full bg-accent" />
            Built by Krishna Keerthan K
          </p>
          <nav aria-label="Footer" className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Link href="/home" className={LINK}>Home</Link>
            <a href="https://github.com/Krishna-Keerthan/HelpHub" target="_blank" rel="noopener noreferrer" className={LINK}>GitHub</a>
            {contact && <a href={contact} className={LINK}>Contact</a>}
          </nav>
        </div>
        <p className={`mt-4 ${captionClass}`}>© {new Date().getFullYear()} Krishna Keerthan K. All rights reserved.</p>
      </footer>
    </div>
  );
}
