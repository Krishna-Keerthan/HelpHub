"use client";

import Link from "next/link";
import { buttonClass, captionClass } from "@/components/ui/styles";
import { useDemoLogin } from "@/lib/ui/use-demo-login";

export function HomeActions({ demoAvailable, children }: { demoAvailable: boolean; children?: React.ReactNode }) {
  const demo = useDemoLogin("/documents");
  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void demo.start()}
          disabled={demo.busy || !demoAvailable}
          className={buttonClass({ variant: "primary" })}
        >
          {demo.busy ? "Starting the demo…" : "Try the demo"}
        </button>
        <Link href="/login" className={buttonClass({ variant: "secondary" })}>
          Sign in
        </Link>
        {children}
      </div>
      {demo.error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {demo.error}
        </p>
      )}
      <p className={`mt-3 ${captionClass}`}>
        {demoAvailable
          ? "The demo is a shared, read-only account; do not enter personal information."
          : "The demo is not configured on this server."}{" "}
        The free tier sleeps when idle, so the first request can take about a minute.
      </p>
    </div>
  );
}
