const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/**
 * CSRF guard for state-changing routes: the Origin header must equal this app's own
 * origin or one listed in ALLOWED_ORIGINS (comma separated). A missing Origin is rejected.
 */
export function originAllowed(req: Request, extra: string[] = allowedOrigins()): boolean {
  if (SAFE_METHODS.has(req.method)) return true;
  const origin = req.headers.get("origin");
  if (!origin) return false;
  return origin === new URL(req.url).origin || extra.includes(origin);
}

export function allowedOrigins(): string[] {
  return (process.env.ALLOWED_ORIGINS ?? "")
    .split(",")
    .map((o) => o.trim())
    .filter(Boolean);
}

export function forbiddenOrigin(): Response {
  return Response.json({ code: "bad_origin" }, { status: 403 });
}
