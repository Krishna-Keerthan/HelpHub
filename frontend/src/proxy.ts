import { NextResponse, type NextRequest } from "next/server";

const REFRESH_COOKIE = "hh_rt";

/**
 * Optimistic route protection: no refresh cookie, no pages. This only checks that the
 * cookie exists; FastAPI still verifies every token. Public: "/" and the home page screenshots in public/home/.
 */
export function proxy(req: NextRequest) {
  // "/" is the public home page (it redirects signed-in visitors itself); the exact path only, nothing under it.
  if (req.nextUrl.pathname === "/") return NextResponse.next();
  if (req.cookies.get(REFRESH_COOKIE)?.value) return NextResponse.next();
  const login = new URL("/login", req.url);
  login.searchParams.set("next", req.nextUrl.pathname + req.nextUrl.search);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!api|login|_next/static|_next/image|favicon.ico|home/).*)"],
};
