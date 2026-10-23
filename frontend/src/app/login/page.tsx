import { Suspense } from "react";
import { LoginForm } from "@/components/LoginForm";
import { WakingBanner } from "@/components/WakingBanner";
import { missingDemoVars } from "@/lib/server/auth-handlers";

// Reads server env per request so the demo button reflects the running configuration.
export const dynamic = "force-dynamic";

export default function LoginPage() {
  return (
    <main className="mx-auto max-w-sm p-4 sm:p-8">
      <WakingBanner />
      <h1 className="mb-6 text-2xl font-semibold">HelpHub</h1>
      <Suspense>
        <LoginForm demoAvailable={missingDemoVars().length === 0} />
      </Suspense>
    </main>
  );
}
