import type { ReactNode } from "react";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { BrandLink } from "./BrandLink";
import { SiteFooter } from "./SiteFooter";
import { SkipLink } from "./SkipLink";
import { StickyHeader } from "./StickyHeader";

export const PUBLIC_WIDTH = "max-w-5xl";

/**
 * Header, main and footer for pages outside the signed-in app (login, 404): the same top row as the home page
 * (wordmark and theme toggle) and the same footer. `mainClass` sets the width and padding of the page body.
 */
export function PublicShell({ mainClass, children }: { mainClass: string; children: ReactNode }) {
  return (
    <>
      <SkipLink />
      <div className="flex min-h-screen flex-col">
        <StickyHeader innerClass={PUBLIC_WIDTH}>
          <BrandLink href="/home" className="mr-auto" />
          <ThemeToggle />
        </StickyHeader>
        <main id="content" tabIndex={-1} className={`mx-auto w-full flex-1 focus:outline-none ${mainClass}`}>
          {children}
        </main>
        <SiteFooter containerClass={PUBLIC_WIDTH} />
      </div>
    </>
  );
}
