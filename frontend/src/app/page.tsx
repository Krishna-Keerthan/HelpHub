import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { HomeActions } from "@/components/HomeActions";
import { RequestAccessLink } from "@/components/RequestAccessLink";
import { Faq } from "@/components/home/Faq";
import { Features } from "@/components/home/Features";
import { HomeFooter } from "@/components/home/HomeFooter";
import { HomeNav } from "@/components/home/HomeNav";
import { MockChat } from "@/components/home/MockChat";
import { chipClass } from "@/components/ui/styles";
import { missingDemoVars } from "@/lib/server/auth-handlers";

// Reads cookies and server env per request: the redirect and the demo button reflect the running configuration.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "HelpHub: answers from your support documents",
  description:
    "A support knowledge engine. Ask a question and get an answer that cites its sources, or a clear refusal when nothing in your documents is relevant. Closed beta.",
};

export default async function Home() {
  if ((await cookies()).get("hh_rt")?.value) redirect("/documents");

  const contactEmail = process.env.NEXT_PUBLIC_CONTACT_EMAIL;
  return (
    <>
      <HomeNav contactEmail={contactEmail} />
      <main className="mx-auto max-w-5xl px-4">
        <section className="relative isolate grid items-center gap-10 py-12 sm:py-20 lg:grid-cols-2">
          {/* Soft accent glow behind the hero: token colour, low opacity, decorative. */}
          <div aria-hidden="true" className="pointer-events-none absolute -top-24 left-1/2 -z-10 h-72 w-[36rem] max-w-full -translate-x-1/2 rounded-full bg-accent/20 blur-3xl" />
          <div>
            <span className={chipClass("sm")}>Closed beta</span>
            <h1 className="mt-5 text-4xl font-semibold tracking-tight sm:text-5xl lg:text-6xl">Answers from your own support documents</h1>
            <p className="mt-5 max-w-xl text-lg text-muted">
              Ask in plain language. Every answer cites the passages it came from, or HelpHub honestly says it found nothing
              instead of guessing.
            </p>
            <div className="mt-8">
              <HomeActions demoAvailable={missingDemoVars().length === 0}>
                <RequestAccessLink contactEmail={contactEmail} />
              </HomeActions>
            </div>
          </div>
          <MockChat />
        </section>
        <Features />
        <Faq />
        <HomeFooter contactEmail={contactEmail} />
      </main>
    </>
  );
}
