import Link from "next/link";
import { contactHref } from "@/lib/request-access";
import { captionClass } from "@/components/ui/styles";

const LINK = "rounded-md text-sm text-muted underline-offset-4 hover:text-fg hover:underline";

export function HomeFooter({ contactEmail, showHome = false }: { contactEmail: string | undefined; showHome?: boolean }) {
  const contact = contactHref(contactEmail);
  return (
    <footer className="mt-8 border-t border-line py-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="flex items-center gap-2 font-medium">
          <span aria-hidden="true" className="h-4 w-1 rounded-full bg-accent" />
          Built by Krishna Keerthan K
        </p>
        <nav aria-label="Footer" className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {showHome && <Link href="/home" className={LINK}>Home</Link>}
          <a href="https://github.com/Krishna-Keerthan/HelpHub" target="_blank" rel="noopener noreferrer" className={LINK}>GitHub</a>
          {contact && <a href={contact} className={LINK}>Contact</a>}
        </nav>
      </div>
      <p className={`mt-4 ${captionClass}`}>© {new Date().getFullYear()} Krishna Keerthan K. All rights reserved.</p>
    </footer>
  );
}
