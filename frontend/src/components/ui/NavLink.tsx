"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** Header link that marks the current section with aria-current="page" and a visible active style. */
export function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const active = pathname === href || (pathname?.startsWith(`${href}/`) ?? false);
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`inline-flex min-h-10 shrink-0 items-center rounded-md px-2 text-sm sm:px-3 font-medium motion-safe:transition-colors ${
        active ? "bg-chip text-fg" : "text-muted hover:bg-chip hover:text-fg"
      }`}
    >
      {children}
    </Link>
  );
}
