"use client";

import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { displayCitations } from "@/lib/ui/citation-display";

// Only these schemes become links. react-markdown's own urlTransform already blanks javascript:, data: and other
// schemes; this is the second check, so a link that is not plainly web or mail is shown as text, never as <a href>.
const SAFE_HREF = /^(https?:\/\/|mailto:)/i;

const components: Components = {
  a: ({ href, children }) =>
    href && SAFE_HREF.test(href) ? (
      <a href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 hover:text-accent">
        {children}
      </a>
    ) : (
      <span>{children}</span>
    ),
  p: ({ children }) => <p className="mt-2 whitespace-pre-line break-words first:mt-0">{children}</p>,
  ul: ({ children }) => <ul className="mt-2 list-disc break-words space-y-1 pl-5 first:mt-0">{children}</ul>,
  ol: ({ children }) => <ol className="mt-2 list-decimal break-words space-y-1 pl-5 first:mt-0">{children}</ol>,
  code: ({ children }) => <code className="rounded bg-chip px-1 font-mono text-[0.9em]">{children}</code>,
  pre: ({ children }) => <pre className="mt-2 overflow-x-auto rounded-md bg-chip p-3 text-sm first:mt-0">{children}</pre>,
  // Answers are chat text, not documents: headings are shown as emphasised paragraphs, images are not loaded.
  h1: ({ children }) => <p className="mt-2 font-semibold first:mt-0">{children}</p>,
  h2: ({ children }) => <p className="mt-2 font-semibold first:mt-0">{children}</p>,
  h3: ({ children }) => <p className="mt-2 font-semibold first:mt-0">{children}</p>,
  h4: ({ children }) => <p className="mt-2 font-semibold first:mt-0">{children}</p>,
  h5: ({ children }) => <p className="mt-2 font-semibold first:mt-0">{children}</p>,
  h6: ({ children }) => <p className="mt-2 font-semibold first:mt-0">{children}</p>,
};

/**
 * An assistant answer as Markdown: paragraphs, **bold**, lists, inline code, links. Raw HTML is never rendered
 * (no rehype-raw, no dangerouslySetInnerHTML), images are dropped, and [n] citation markers stay visible text.
 * Memoised by text, so a streaming token re-renders only the message that changed.
 */
export const AnswerMarkdown = memo(function AnswerMarkdown({ text }: { text: string }) {
  return (
    // No wrapper element: the blocks land directly in the caller's live region (the chat tests rely on that).
    <ReactMarkdown components={components} disallowedElements={["img"]}>
      {displayCitations(text)}
    </ReactMarkdown>
  );
});
