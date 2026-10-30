import { NextResponse, type NextRequest } from "next/server";

const REFRESH_COOKIE = "hh_rt";
const PUBLIC_PATHS = new Set(["/", "/home"]);

/**
 * Optimistic route protection: no refresh cookie, no pages. This only checks that the
 * cookie exists; FastAPI still verifies every token. Public: "/" and "/home" only.
 */
export function proxy(req: NextRequest) {
  // "/" and "/home" are the public home page ("/" redirects signed-in visitors itself); exact paths only, nothing under them.
  if (PUBLIC_PATHS.has(req.nextUrl.pathname)) return NextResponse.next();
  if (req.cookies.get(REFRESH_COOKIE)?.value) return NextResponse.next();
  const login = new URL("/login", req.url);
  login.searchParams.set("next", req.nextUrl.pathname + req.nextUrl.search);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!api|login|_next/static|_next/image|favicon.ico).*)"],
};
