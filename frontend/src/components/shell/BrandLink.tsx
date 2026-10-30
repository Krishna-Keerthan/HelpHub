import Link from "next/link";

/** The wordmark. A link on every page: to the app inside it, to the home page outside it. */
export function BrandLink({ href, className = "" }: { href: string; className?: string }) {
  return (
    <Link href={href} className={`inline-flex min-h-10 shrink-0 items-center rounded-md font-semibold tracking-tight ${className}`}>
      HelpHub
    </Link>
  );
}
