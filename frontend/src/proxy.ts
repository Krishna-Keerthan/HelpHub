import { NextResponse, type NextRequest } from "next/server";

const REFRESH_COOKIE = "hh_rt";

/**
 * Optimistic route protection: no refresh cookie, no pages. This only checks that the
 * cookie exists; FastAPI still verifies every token.
 */
export function proxy(req: NextRequest) {
  if (req.cookies.get(REFRESH_COOKIE)?.value) return NextResponse.next();
  const login = new URL("/login", req.url);
  const next = req.nextUrl.pathname + req.nextUrl.search;
  if (next !== "/") login.searchParams.set("next", next);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!api|login|_next/static|_next/image|favicon.ico).*)"],
};
