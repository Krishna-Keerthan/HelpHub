import { useEffect, useRef, type RefObject } from "react";

/** The end marker this close below the bottom of the screen (or anywhere above it) counts as "at the bottom". */
export const NEAR_BOTTOM_PX = 120;

/**
 * How far below the visible area the marker is (negative: it is on screen). Measured from the marker, not from the
 * end of the document: the footer, the sticky composer and the page padding sit below the last message, so the
 * document's end is never close to it.
 */
export const pxBelowFold = (marker: Element): number => marker.getBoundingClientRect().top - window.innerHeight;

/**
 * Keeps the end marker in view when `changeKey` changes (a restored history, a new message, a streamed token),
 * but only while the reader is near the bottom: someone who scrolled up to re-read is not dragged back down.
 * `follow()` re-arms it (call it when the user sends a question, so their own message and the answer are shown).
 * Give the marker a `scroll-mb-*` at least as tall as the sticky composer, so the scroll leaves the last message
 * above the composer instead of under it.
 */
export function useStickToBottom(changeKey: unknown, enabled: boolean): { endRef: RefObject<HTMLDivElement | null>; follow: () => void } {
  const endRef = useRef<HTMLDivElement>(null);
  const stuck = useRef(true);

  useEffect(() => {
    const onScroll = () => {
      if (endRef.current) stuck.current = pxBelowFold(endRef.current) <= NEAR_BOTTOM_PX;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (enabled && stuck.current) endRef.current?.scrollIntoView?.({ block: "end" });
  }, [changeKey, enabled]);

  return { endRef, follow: () => void (stuck.current = true) };
}
