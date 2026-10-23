import type { NextResponse } from "next/server";
import { tokenExpiry } from "./jwt";

export const ACCESS_COOKIE = "hh_at";
export const REFRESH_COOKIE = "hh_rt";
const REFRESH_MAX_AGE = 7 * 24 * 60 * 60;

type CookieJar = { get(name: string): { value: string } | undefined };

export function readCookie(jar: CookieJar, name: string): string | null {
  return jar.get(name)?.value || null;
}

/** Secure everywhere except plain-http localhost dev. */
function secure(reqUrl: string): boolean {
  const u = new URL(reqUrl);
  return !(u.protocol === "http:" && (u.hostname === "localhost" || u.hostname === "127.0.0.1"));
}

export function setSessionCookies(
  res: NextResponse,
  reqUrl: string,
  pair: { access_token: string; refresh_token: string },
  nowMs: number = Date.now(),
): void {
  const base = { httpOnly: true, sameSite: "lax" as const, secure: secure(reqUrl), path: "/" };
  const exp = tokenExpiry(pair.access_token);
  const accessAge = exp ? Math.max(1, Math.floor(exp - nowMs / 1000)) : 15 * 60;
  res.cookies.set(ACCESS_COOKIE, pair.access_token, { ...base, maxAge: accessAge });
  res.cookies.set(REFRESH_COOKIE, pair.refresh_token, { ...base, maxAge: REFRESH_MAX_AGE });
}

export function clearSessionCookies(res: NextResponse, reqUrl: string): void {
  const base = { httpOnly: true, sameSite: "lax" as const, secure: secure(reqUrl), path: "/", maxAge: 0 };
  res.cookies.set(ACCESS_COOKIE, "", base);
  res.cookies.set(REFRESH_COOKIE, "", base);
}
