import type { ReactNode } from "react";
import { WakingBanner } from "@/components/WakingBanner";

/**
 * The one top bar. Sticky, opaque enough to read over content (a slight blur is added), above page content and
 * the chat composer (z-10) and below anything that would be a dialog (z-30 and up). `innerClass` carries the
 * width rule of the page. The "service is waking up" notice lives inside it, below the bar's row(s), so it stays in
 * view while the page scrolls instead of scrolling away above a header that has already stuck.
 */
export function StickyHeader({ innerClass, children }: { innerClass: string; children: ReactNode }) {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-surface-raised/95 backdrop-blur">
      <div className={`mx-auto flex flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2 ${innerClass}`}>{children}</div>
      <WakingBanner />
    </header>
  );
}
