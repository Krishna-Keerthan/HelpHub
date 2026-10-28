"use client";

import { useMe } from "@/lib/query/hooks";
import { NavLink } from "./ui/NavLink";

/** Fail closed (D11, D17): shown only once /auth/me has confirmed the admin role. */
export function UsersNavLink() {
  const me = useMe();
  if (me.status !== "success" || me.data.role !== "admin") return null;
  return <NavLink href="/users">Users</NavLink>;
}
