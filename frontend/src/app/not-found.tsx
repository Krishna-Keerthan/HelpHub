import type { Metadata } from "next";
import Link from "next/link";
import { buttonClass } from "@/components/ui/styles";

// The root title template turns this into "Page not found · HelpHub".
export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <main className="mx-auto max-w-md p-4 py-16 text-center">
      <p className="font-semibold tracking-tight">HelpHub</p>
      <h1 className="mt-6 text-2xl font-semibold tracking-tight">This page could not be found.</h1>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Link href="/home" className={buttonClass({ variant: "primary" })}>Home</Link>
        <Link href="/documents" className={buttonClass({ variant: "secondary" })}>Documents</Link>
      </div>
    </main>
  );
}
