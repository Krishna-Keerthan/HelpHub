"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { demoLogin } from "@/lib/api/client";
import { failureMessage } from "./failure";

/** The "Try the demo" flow shared by the login form and the home page: log in as the demo viewer, then go to `next`. */
export function useDemoLogin(next: string) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const result = await demoLogin();
      if (result.ok) {
        router.replace(next);
        return;
      }
      setError(
        result.code === "demo_unavailable"
          ? "The demo is not available right now."
          : failureMessage(result.status, result.code, result.retryAfter),
      );
    } catch {
      setError("Could not reach the service. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return { busy, error, start, clearError: () => setError(null) };
}
