// WCAG 2.x contrast of the token pairs in src/app/globals.css (light and dark sides of light-dark()).
// Checks token pairs only, not the rendered page. Usage: node scripts/contrast.mjs [css file]
import { readFileSync } from "node:fs";

// Optional first argument: another CSS file to check (the tests use it for a negative control).
const cssPath = process.argv[2] ?? new URL("../src/app/globals.css", import.meta.url);
const css = readFileSync(cssPath, "utf8");

// Each token is `--name: light-dark(<light hex>, <dark hex>);` in the first `:root { }` block.
const rootBlock = css.match(/:root\s*{([^}]*)}/)[1];
const light = {};
const dark = {};
for (const m of rootBlock.matchAll(/--([\w-]+):\s*light-dark\(\s*(#[0-9a-fA-F]{6})\s*,\s*(#[0-9a-fA-F]{6})\s*\)\s*;/g)) {
  light[m[1]] = m[2];
  dark[m[1]] = m[3];
}
// A token that is not in light-dark() form would be skipped silently, so count declarations too.
const declared = [...rootBlock.matchAll(/--[\w-]+:/g)].length;
if (declared !== Object.keys(light).length || declared === 0) {
  console.error(`${declared} tokens declared in :root but ${Object.keys(light).length} parsed as light-dark(#hex, #hex)`);
  process.exit(1);
}
// The theme switch itself: an explicit data-theme must pin color-scheme to one side.
for (const t of ["light", "dark"]) {
  if (!new RegExp(`:root\\[data-theme="${t}"\\]\\s*{[^}]*color-scheme:\\s*${t}\\s*;`).test(css)) {
    console.error(`missing :root[data-theme="${t}"] { color-scheme: ${t} }`);
    process.exit(1);
  }
}

const lum = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

// [foreground token, background token, minimum ratio, where it is used]
const PAIRS = [
  ["fg", "surface", 4.5, "body text"],
  ["fg", "surface-raised", 4.5, "cards, panels"],
  ["fg", "chip", 4.5, "citation chips, ghost hover"],
  ["muted", "surface", 4.5, "hints, empty states"],
  ["muted", "surface-raised", 4.5, "hints inside cards"],
  ["muted", "chip", 4.5, "nav links on hover, neutral status pill"],
  ["accent-fg", "accent", 4.5, "primary buttons, skip link"],
  ["accent-fg", "accent-hover", 4.5, "primary button hover"],
  ["danger", "surface", 4.5, "error text, delete button"],
  ["danger", "surface-raised", 4.5, "error text inside cards"],
  ["danger", "bad-bg", 4.5, "delete button hover"],
  ["ok", "ok-bg", 4.5, "READY pill"],
  ["warn", "warn-bg", 4.5, "PENDING pill"],
  ["bad", "bad-bg", 4.5, "FAILED pill"],
  ["info-fg", "info", 4.5, "status notices"],
  ["accent", "surface", 3, "focus ring (non-text, 3:1)"],
  ["accent", "surface-raised", 3, "focus ring inside cards (non-text, 3:1)"],
  ["control-border", "surface", 3, "input/button borders (non-text, 3:1)"],
  ["control-border", "surface-raised", 3, "controls inside cards (non-text, 3:1)"],
];
// Reported but not enforced: --line is decorative only (dividers, dashed placeholders), not a control border.
const INFO_PAIRS = [["line", "surface", 3, "decorative dividers"]];

let failed = 0;
console.log("theme  pair                    ratio  min   result");
for (const [name, theme] of [["light", light], ["dark", dark]]) {
  for (const [fg, bg, min, use] of PAIRS) {
    const r = ratio(theme[fg], theme[bg]);
    const ok = r >= min;
    if (!ok) failed++;
    console.log(`${name.padEnd(6)} ${`${fg} on ${bg}`.padEnd(23)} ${r.toFixed(2).padStart(5)}  ${String(min).padEnd(4)}  ${ok ? "pass" : "FAIL"}  (${use})`);
  }
}
for (const [name, theme] of [["light", light], ["dark", dark]]) {
  for (const [fg, bg, min, use] of INFO_PAIRS) {
    const r = ratio(theme[fg], theme[bg]);
    console.log(`${name.padEnd(6)} ${`${fg} on ${bg}`.padEnd(23)} ${r.toFixed(2).padStart(5)}  ${String(min).padEnd(4)}  ${r >= min ? "pass" : "BELOW"}  (${use}, info only)`);
  }
}
process.exit(failed ? 1 : 0);
