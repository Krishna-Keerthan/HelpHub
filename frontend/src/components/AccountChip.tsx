"use client";

import { useMe } from "@/lib/query/hooks";

/**
 * Who is signed in: email and role, from the shared /auth/me query (no second fetch). Display only; the write
 * controls keep their own fail-closed role check (D11). Pending shows a fixed-size placeholder so the header does
 * not jump; a failed lookup shows nothing. On phones it takes its own row under the nav and the email truncates.
 */
export function AccountChip() {
  const me = useMe();
  if (me.status === "error") return null;
  if (me.status === "pending") {
    return <div aria-hidden="true" data-testid="account-chip-placeholder" className="order-4 h-6 w-44 max-w-full basis-full rounded-md bg-chip sm:order-3 sm:basis-auto" />;
  }
  const { email, role } = me.data;
  return (
    <div className="order-4 flex h-6 min-w-0 max-w-full basis-full items-center gap-2 text-xs sm:order-3 sm:max-w-[16rem] sm:basis-auto">
      {email && <span title={email} className="min-w-0 truncate text-muted">{email}</span>}
      <span className="shrink-0 rounded-full border border-line bg-chip px-2 py-0.5 font-medium capitalize text-fg">{role}</span>
    </div>
  );
}
