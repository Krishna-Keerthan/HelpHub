"use client";

import { useEffect, useState } from "react";
import { onServiceWaking } from "@/lib/api/authed-fetch";

export function WakingBanner() {
  const [waking, setWaking] = useState(false);
  useEffect(() => onServiceWaking(setWaking), []);
  if (!waking) return null;
  return (
    <div role="status" className="bg-amber-100 px-4 py-2 text-sm text-amber-900">
      The service is waking up. This can take up to a minute.
    </div>
  );
}
