import { expect, test } from "vitest";
import { otherTheme, parseTheme, THEME_COOKIE, themeCookie } from "./theme";

test("parseTheme accepts only light and dark", () => {
  expect(parseTheme("light")).toBe("light");
  expect(parseTheme("dark")).toBe("dark");
  for (const bad of [undefined, null, "", "Dark", "auto", "dark; Path=/", "light ", "1"]) expect(parseTheme(bad)).toBeUndefined();
});

test("otherTheme flips", () => {
  expect(otherTheme("light")).toBe("dark");
  expect(otherTheme("dark")).toBe("light");
});

test("the cookie is named hh_theme and carries the word, Path=/, one year and SameSite=Lax", () => {
  expect(THEME_COOKIE).toBe("hh_theme");
  const c = themeCookie("dark", false);
  expect(c).toBe("hh_theme=dark; Path=/; Max-Age=31536000; SameSite=Lax");
  expect(c).not.toMatch(/HttpOnly/i);
});

test("Secure is added only on https", () => {
  expect(themeCookie("light", true)).toBe("hh_theme=light; Path=/; Max-Age=31536000; SameSite=Lax; Secure");
  expect(themeCookie("light", false)).not.toContain("Secure");
});
