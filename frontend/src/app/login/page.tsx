import { Suspense } from "react";
import { LoginForm } from "@/components/LoginForm";
import { WakingBanner } from "@/components/WakingBanner";

export default function LoginPage() {
  return (
    <main className="mx-auto max-w-sm p-8">
      <WakingBanner />
      <h1 className="mb-6 text-2xl font-semibold">HelpHub</h1>
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
