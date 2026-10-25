/** Read the `exp` claim (seconds) of a JWT without verifying it. A hint only: FastAPI verifies. */
export function tokenExpiry(token: string): number | null {
  const part = token.split(".")[1];
  if (!part) return null;
  try {
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = (JSON.parse(json) as { exp?: unknown }).exp;
    return typeof exp === "number" ? exp : null;
  } catch {
    return null;
  }
}

/** True when the token has no readable exp or is within `skewSeconds` of expiring. */
export function isExpired(token: string, nowMs: number, skewSeconds = 5): boolean {
  const exp = tokenExpiry(token);
  return exp === null || exp - skewSeconds <= nowMs / 1000;
}
