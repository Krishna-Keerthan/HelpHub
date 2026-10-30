"use client";

import { useMe } from "@/lib/query/hooks";

/**
 * Who is signed in: email and role, from the shared /auth/me query (no second fetch). Display only; the write
 * controls keep their own fail-closed role check (D11). Pending shows a fixed-size placeholder so the header does
 * not jump; a failed lookup shows nothing. It sits in the header's action group beside the theme toggle and Log out.
 * Below sm only the role badge is visible (the email stays in the DOM for screen readers and in the badge's title);
 * from sm up the email shows, truncated, beside it.
 */
export function AccountChip() {
  const me = useMe();
  if (me.status === "error") return null;
  if (me.status === "pending") {
    return <div aria-hidden="true" data-testid="account-chip-placeholder" className="h-6 w-16 rounded-md bg-chip sm:w-40" />;
  }
  const { email, role } = me.data;
  return (
    <div className="flex h-6 min-w-0 items-center gap-2 text-xs">
      {email && <span title={email} className="min-w-0 truncate text-muted max-sm:sr-only sm:max-w-[10rem]">{email}</span>}
      <span title={email ?? undefined} className="shrink-0 rounded-full border border-line bg-chip px-2 py-0.5 font-medium capitalize text-fg">{role}</span>
    </div>
  );
}
