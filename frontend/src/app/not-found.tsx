import type { Metadata } from "next";
import Link from "next/link";
import { PublicShell } from "@/components/shell/PublicShell";
import { buttonClass } from "@/components/ui/styles";

// The root title template turns this into "Page not found · HelpHub".
export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <PublicShell mainClass="max-w-md p-4 py-16 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">This page could not be found.</h1>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Link href="/home" className={buttonClass({ variant: "primary" })}>Home</Link>
        <Link href="/documents" className={buttonClass({ variant: "secondary" })}>Documents</Link>
      </div>
    </PublicShell>
  );
}
