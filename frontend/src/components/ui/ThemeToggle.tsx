"use client";

import { useSyncExternalStore } from "react";
import { buttonClass } from "@/components/ui/styles";
import { otherTheme, parseTheme, THEME_CHANGED_EVENT, themeCookie, type Theme } from "@/lib/theme";

const DARK_QUERY = "(prefers-color-scheme: dark)";

/** The explicit choice on <html data-theme>, else the OS preference. */
function effectiveTheme(): Theme {
  const set = parseTheme(document.documentElement.dataset.theme);
  if (set) return set;
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

function subscribe(onChange: () => void): () => void {
  const media = typeof window.matchMedia === "function" ? window.matchMedia(DARK_QUERY) : null;
  media?.addEventListener("change", onChange);
  window.addEventListener(THEME_CHANGED_EVENT, onChange);
  return () => {
    media?.removeEventListener("change", onChange);
    window.removeEventListener(THEME_CHANGED_EVENT, onChange);
  };
}

// null on the server and during hydration: the placeholder below renders then, so there is no mismatch.
const serverTheme = (): Theme | null => null;

function choose(theme: Theme): void {
  document.cookie = themeCookie(theme, window.location.protocol === "https:");
  document.documentElement.dataset.theme = theme;
  window.dispatchEvent(new Event(THEME_CHANGED_EVENT));
}

const ICON = "h-5 w-5";

function SunIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className={ICON}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={ICON}>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

/** Icon button that flips light/dark. The icon is the theme it switches to; the label says the same. */
export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, effectiveTheme, serverTheme);
  if (theme === null) {
    // Same 40x40 box as the button, so nothing moves when it appears.
    return <span aria-hidden="true" className="inline-block h-10 w-10" data-testid="theme-toggle-placeholder" />;
  }
  const next = otherTheme(theme);
  return (
    <button
      type="button"
      aria-label={`Switch to ${next} theme`}
      className={buttonClass({ variant: "ghost", icon: true })}
      onClick={() => choose(next)}
    >
      {next === "light" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}
