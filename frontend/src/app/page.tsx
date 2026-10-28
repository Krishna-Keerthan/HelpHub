import type { Metadata } from "next";
import { cookies } from "next/headers";
import Image from "next/image";
import { redirect } from "next/navigation";
import { HomeActions } from "@/components/HomeActions";
import { RequestAccessLink } from "@/components/RequestAccessLink";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { captionClass, chipClass, panelClass } from "@/components/ui/styles";
import { missingDemoVars } from "@/lib/server/auth-handlers";

// Reads cookies and server env per request: the redirect and the demo button reflect the running configuration.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "HelpHub: answers from your support documents",
  description:
    "A support knowledge engine. Ask a question and get an answer that cites its sources, or a clear refusal when nothing in your documents is relevant. Closed beta.",
};

const SHOTS = [
  { src: "/home/chat-dark.png", width: 1651, height: 850, alt: "Chat: a question answered with citations to the documents it came from, shown in the dark theme.", caption: "Chat with cited answers" },
  { src: "/home/compare-light.png", width: 1406, height: 911, alt: "Compare: the same query run through different search modes, results side by side in the light theme.", caption: "Compare search modes" },
  { src: "/home/documents-dark.png", width: 1352, height: 910, alt: "Documents: the workspace's uploaded files with their processing status, shown in the dark theme.", caption: "Your documents" },
];

export default async function Home() {
  if ((await cookies()).get("hh_rt")?.value) redirect("/documents");

  return (
    <main className="mx-auto max-w-4xl p-4 sm:py-10">
      <div className="flex items-center justify-between">
        <span className="font-semibold tracking-tight">HelpHub</span>
        <ThemeToggle />
      </div>
      <section className="mt-8">
        <span className={chipClass("sm")}>Closed beta</span>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">Answers from your own support documents</h1>
        <p className="mt-4 max-w-2xl text-base text-muted">
          Upload your help articles and policies, then ask questions in plain language. Every answer cites the passages it
          came from. When nothing in your documents is relevant, HelpHub says so instead of guessing.
        </p>
        <div className="mt-6">
          <HomeActions demoAvailable={missingDemoVars().length === 0}>
            <RequestAccessLink contactEmail={process.env.NEXT_PUBLIC_CONTACT_EMAIL} />
          </HomeActions>
        </div>
      </section>
      <section aria-label="Screenshots" className="mt-10 grid gap-6">
        {SHOTS.map((s, i) => (
          <figure key={s.src} className={`overflow-hidden ${panelClass}`}>
            <Image src={s.src} width={s.width} height={s.height} alt={s.alt} sizes="(min-width: 896px) 896px, 100vw" priority={i === 0} className="h-auto w-full" />
            <figcaption className={`p-3 ${captionClass}`}>{s.caption}</figcaption>
          </figure>
        ))}
      </section>
    </main>
  );
}
