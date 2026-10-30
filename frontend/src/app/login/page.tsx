import type { Metadata } from "next";
import { Suspense } from "react";
import { LoginForm } from "@/components/LoginForm";
import { PublicShell } from "@/components/shell/PublicShell";
import { panelClass } from "@/components/ui/styles";
import { missingDemoVars } from "@/lib/server/auth-handlers";

// Reads server env per request so the demo button reflects the running configuration.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to your HelpHub workspace, or try the read-only demo.",
};

export default function LoginPage() {
  return (
    <PublicShell mainClass="max-w-sm p-4 sm:py-12">
      <div className={`p-6 ${panelClass}`}>
        <h1 className="mb-6 text-center text-2xl font-semibold tracking-tight">HelpHub</h1>
        <Suspense>
          <LoginForm demoAvailable={missingDemoVars().length === 0} />
        </Suspense>
      </div>
    </PublicShell>
  );
}
