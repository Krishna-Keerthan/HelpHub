"use client";

import { useState } from "react";
import { logout } from "@/lib/api/client";

export function LogoutButton() {
  const [busy, setBusy] = useState(false);
  return (
    <button
      type="button"
      disabled={busy}
      className="min-h-10 px-1 text-sm underline disabled:opacity-50"
      onClick={async () => {
        setBusy(true);
        try {
          await logout();
        } catch {
          // The server call failed; the client cache is already cleared. Still leave the page.
        } finally {
          // Full navigation on purpose: drops all in-memory client state after logout.
          // eslint-disable-next-line @next/next/no-location-assign-relative-destination
          window.location.assign("/login");
        }
      }}
    >
      Log out
    </button>
  );
}
