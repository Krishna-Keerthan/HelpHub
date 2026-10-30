/** First focusable element of every page; its target is the `<main id="content">`. */
export function SkipLink() {
  return (
    <a
      href="#content"
      className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-30 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-accent-fg"
    >
      Skip to content
    </a>
  );
}
