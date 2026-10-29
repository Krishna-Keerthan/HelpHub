import { cardClass, headingClass } from "@/components/ui/styles";

// Each entry is something the code does today (evidence is in the PR notes).
export const FEATURES = [
  { title: "Cited answers", text: "Chat answers point to the passages and documents they came from, shown as source chips." },
  { title: "Honest “not found”", text: "Unrelated questions are refused. Close-but-unanswered questions can still get an answer built from the nearest passages, so check the cited sources." },
  { title: "Compare search modes", text: "Run the same query through vector, keyword and hybrid search and see the results side by side." },
  { title: "Document upload", text: "Upload .txt, .md and .pdf files; each shows its processing status (pending, ready or failed)." },
  { title: "Separate workspaces", text: "Every workspace is its own tenant: its data is filtered by tenant and protected by row-level security in the database." },
  { title: "Roles", text: "Admins manage users and documents, agents upload documents, viewers read, chat and search." },
  { title: "Dark and light themes", text: "Follows your system setting, or switch with the toggle; your choice is remembered." },
] as const;

export function Features() {
  return (
    <section id="features" aria-labelledby="features-title" className="scroll-mt-20 py-12">
      <h2 id="features-title" className="text-2xl font-semibold tracking-tight sm:text-3xl">What it does</h2>
      <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f) => (
          <li key={f.title} className={cardClass}>
            <h3 className={headingClass}>{f.title}</h3>
            <p className="mt-2 text-sm text-muted">{f.text}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
