/**
 * Theme preference. The only thing stored is the word "light" or "dark" in the hh_theme cookie. It is not
 * sensitive and not HttpOnly (the client sets it). No cookie means: follow the OS (prefers-color-scheme).
 */
export const THEME_COOKIE = "hh_theme";
export const THEME_CHANGED_EVENT = "hh-theme-changed";
const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

export type Theme = "light" | "dark";

/** Anything other than the two allowed words is ignored. */
export function parseTheme(value: string | null | undefined): Theme | undefined {
  return value === "light" || value === "dark" ? value : undefined;
}

export function otherTheme(theme: Theme): Theme {
  return theme === "dark" ? "light" : "dark";
}

/** The `document.cookie` string for a preference: SameSite=Lax, Path=/, one year, Secure on https. */
export function themeCookie(theme: Theme, secure: boolean): string {
  return `${THEME_COOKIE}=${theme}; Path=/; Max-Age=${ONE_YEAR_SECONDS}; SameSite=Lax${secure ? "; Secure" : ""}`;
}
