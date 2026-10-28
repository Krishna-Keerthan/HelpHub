import { captionClass, cardClass, chipClass } from "@/components/ui/styles";

/** HTML/CSS-only illustration of a question, a cited answer and a source chip. Generic text, no real data. */
export function MockChat() {
  return (
    <div aria-hidden="true" data-testid="mock-chat" className={`mx-auto w-full max-w-md space-y-3 shadow-lg ${cardClass}`}>
      <p className={captionClass}>Illustration, not real data</p>
      <div className="ml-auto w-fit max-w-[85%] rounded-lg bg-accent px-3 py-2 text-sm text-accent-fg">How do I change my plan?</div>
      <div className="max-w-[92%] rounded-lg border border-line bg-surface px-3 py-2 text-sm">
        <p>Open your account settings and choose a new plan. The change applies from the next billing date [1].</p>
        <span className={`mt-2 ${chipClass("sm")}`}>[1] Example document</span>
      </div>
      <div className="max-w-[92%] rounded-lg border border-dashed border-line px-3 py-2 text-sm text-muted">
        If nothing relevant is found: &ldquo;I couldn&rsquo;t find anything that answers this question.&rdquo;
      </div>
    </div>
  );
}
