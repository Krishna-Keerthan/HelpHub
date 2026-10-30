"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { login } from "@/lib/api/client";
import { failureMessage, safeNext } from "@/lib/ui/failure";
import { useDemoLogin } from "@/lib/ui/use-demo-login";
import { buttonClass, captionClass, inputClass } from "./ui/styles";

export function LoginForm({ demoAvailable = false }: { demoAvailable?: boolean }) {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const expired = params.get("reason") === "expired";
  const demo = useDemoLogin(next);
  const [formError, setFormError] = useState<string | null>(null);
  const [formBusy, setFormBusy] = useState(false);
  const error = formError ?? demo.error;
  const busy = formBusy || demo.busy;

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setFormBusy(true);
    setFormError(null);
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
      setFormError(
        result.code === "invalid_credentials"
          ? "Email, password or workspace is wrong."
          : result.status === 422
            ? "Check that every field is filled in correctly."
            : failureMessage(result.status, result.code, result.retryAfter),
      );
    } catch {
      setFormError("Could not reach the service. Check your connection and try again.");
    } finally {
      setFormBusy(false);
    }
  }

  const input = `mt-1 w-full ${inputClass}`;
  return (
    <>
    {expired && (
      <p role="status" className="mb-4 text-sm text-muted">Your session ended. Please sign in again.</p>
    )}
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
        className={buttonClass({ variant: "primary", block: true })}
      >
        {busy ? "Logging in…" : "Log in"}
      </button>
    </form>
    <div className="mt-6 border-t border-line pt-4">
      <button
        type="button"
        onClick={() => { setFormError(null); void demo.start(); }}
        disabled={busy || !demoAvailable}
        className={buttonClass({ variant: "secondary", block: true })}
      >
        Try the demo
      </button>
      <p className={`mt-2 ${captionClass}`}>
        {demoAvailable
          ? "The demo is a shared, read-only account. Other visitors may see your conversations, so do not enter personal information."
          : "The demo is not configured on this server."}
      </p>
    </div>
    </>
  );
}
