"use client";

import { buttonClass } from "@/components/ui/styles";

/** Route error boundary for the app shell. It never shows the error: no message, no stack. */
export default function AppError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div role="alert" className="py-8">
      <h1 className="text-xl font-semibold tracking-tight">Something went wrong.</h1>
      <p className="mt-2 text-muted">The page could not be shown. Try again; if it keeps happening, come back in a minute.</p>
      <button type="button" onClick={reset} className={`mt-4 ${buttonClass({ variant: "primary" })}`}>Try again</button>
    </div>
  );
}
