import { useEffect, useRef, type RefObject } from "react";

/** Closer than this to the bottom of the page counts as "at the bottom" (about two lines of text). */
export const NEAR_BOTTOM_PX = 120;

export const distanceFromBottom = (): number =>
  document.documentElement.scrollHeight - (window.scrollY + window.innerHeight);

/**
 * Keeps the end marker in view when `changeKey` changes (a restored history, a new message, a streamed token),
 * but only while the reader is near the bottom: someone who scrolled up to re-read is not dragged back down.
 * `follow()` re-arms it (call it when the user sends a question, so their own message and the answer are shown).
 */
export function useStickToBottom(changeKey: unknown, enabled: boolean): { endRef: RefObject<HTMLDivElement | null>; follow: () => void } {
  const endRef = useRef<HTMLDivElement>(null);
  const stuck = useRef(true);

  useEffect(() => {
    const onScroll = () => {
      stuck.current = distanceFromBottom() <= NEAR_BOTTOM_PX;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (enabled && stuck.current) endRef.current?.scrollIntoView?.({ block: "end" });
  }, [changeKey, enabled]);

  return { endRef, follow: () => void (stuck.current = true) };
}
