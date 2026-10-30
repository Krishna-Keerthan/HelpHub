import { panelClass } from "@/components/ui/styles";

export const FAQ = [
  { q: "How do I get access?", a: "HelpHub is in closed beta and has no public sign-up. Request access by email; the operator creates your workspace and its first admin, and that admin then adds teammates." },
  { q: "What happens when my documents do not contain the answer?", a: "Unrelated questions are refused with a not-found reply. Close-but-unanswered questions can still get an answer built from the nearest passages, so check the cited sources." },
  { q: "Are workspaces isolated from each other?", a: "Yes in design: every record belongs to a tenant, queries filter by tenant, and the database enforces row-level security on top." },
  { q: "Which files can I upload, and how big?", a: "Plain text (.txt), Markdown (.md) and PDF (.pdf). In this app a file can be up to 4 MB, and the extracted text is limited to about 500,000 characters." },
  { q: "What can each role do?", a: "Admins add users and can upload and delete documents. Agents can upload documents. Viewers are read-only: they can read documents, chat and search." },
  { q: "What is the demo account?", a: "A shared, read-only account. Other visitors may see your conversations, so do not enter personal information." },
  { q: "Why is the first request slow?", a: "The backend runs on a free tier that sleeps when idle, so the first request after a pause can take about a minute." },
] as const;

export function Faq() {
  return (
    <section id="faq" aria-labelledby="faq-title" className="py-12">
      <h2 id="faq-title" className="text-2xl font-semibold tracking-tight sm:text-3xl">Questions</h2>
      <div className={`mt-6 divide-y divide-line px-4 ${panelClass}`}>
        {FAQ.map((item) => (
          <details key={item.q} className="group py-1">
            <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-4 rounded-md py-2 font-medium [&::-webkit-details-marker]:hidden">
              {item.q}
              <svg aria-hidden="true" viewBox="0 0 20 20" width="20" height="20" className="shrink-0 text-muted motion-safe:transition-transform group-open:rotate-180">
                <path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </summary>
            <p className="pb-3 text-sm text-muted">{item.a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
