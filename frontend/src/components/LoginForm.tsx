"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { demoLogin, login } from "@/lib/api/client";
import { failureMessage, safeNext } from "@/lib/ui/failure";

export function LoginForm({ demoAvailable = false }: { demoAvailable?: boolean }) {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const result = await login({
        email: String(f.get("email")),
        password: String(f.get("password")),
        tenant_slug: String(f.get("tenant_slug")),
      });
      if (result.ok) {
        router.replace(next);
        return;
      }
      setError(
        result.code === "invalid_credentials"
          ? "Email, password or workspace is wrong."
          : result.status === 422
            ? "Check that every field is filled in correctly."
            : failureMessage(result.status, result.code, result.retryAfter),
      );
    } catch {
      setError("Could not reach the service. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function onDemo() {
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

  const input = "mt-1 min-h-10 w-full rounded border border-control-border bg-surface px-3 py-2 text-fg";
  return (
    <>
    <form onSubmit={onSubmit} className="space-y-4" aria-label="Log in">
      <label className="block text-sm">
        Workspace
        <input name="tenant_slug" required autoComplete="organization" className={input} />
      </label>
      <label className="block text-sm">
        Email
        <input name="email" type="email" required autoComplete="username" className={input} />
      </label>
      <label className="block text-sm">
        Password
        <input name="password" type="password" required autoComplete="current-password" className={input} />
      </label>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={busy}
        className="min-h-10 w-full rounded bg-accent px-3 py-2 text-accent-fg disabled:opacity-50"
      >
        {busy ? "Logging in…" : "Log in"}
      </button>
    </form>
    <div className="mt-6 border-t border-line pt-4">
      <button
        type="button"
        onClick={() => void onDemo()}
        disabled={busy || !demoAvailable}
        className="min-h-10 w-full rounded border border-control-border px-3 py-2 disabled:opacity-50"
      >
        Try the demo
      </button>
      <p className="mt-2 text-xs text-muted">
        {demoAvailable
          ? "The demo is a shared, read-only account. Other visitors may see your conversations, so do not enter personal information."
          : "The demo is not configured on this server."}
      </p>
    </div>
    </>
  );
}
