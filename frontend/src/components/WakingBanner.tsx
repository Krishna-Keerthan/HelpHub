"use client";

import { useEffect, useState } from "react";
import { onServiceWaking } from "@/lib/api/authed-fetch";
import { Notice } from "./Notice";

export function WakingBanner() {
  const [waking, setWaking] = useState(false);
  useEffect(() => onServiceWaking(setWaking), []);
  if (!waking) return null;
  return <Notice>The service is waking up. This can take up to a minute.</Notice>;
}
