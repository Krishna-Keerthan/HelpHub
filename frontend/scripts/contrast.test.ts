// @vitest-environment node
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "vitest";

const script = join(__dirname, "contrast.mjs");
const realCss = join(__dirname, "../src/app/globals.css");

function run(cssFile?: string) {
  const r = spawnSync(process.execPath, cssFile ? [script, cssFile] : [script], { encoding: "utf8" });
  return { code: r.status, out: r.stdout + r.stderr };
}

function variant(edit: (css: string) => string): string {
  const file = join(mkdtempSync(join(tmpdir(), "contrast-")), "globals.css");
  writeFileSync(file, edit(readFileSync(realCss, "utf8")));
  return file;
}

test("the real globals.css passes in both themes", () => {
  const { code, out } = run();
  expect(code).toBe(0);
  expect(out).toMatch(/^light .*fg on surface .*pass/m);
  expect(out).toMatch(/^dark .*fg on surface .*pass/m);
});

test("negative control: a light-side token that drops below 4.5:1 fails the script", () => {
  const { code, out } = run(variant((css) => css.replace("--muted: light-dark(#52525b,", "--muted: light-dark(#a1a1aa,")));
  expect(code).toBe(1);
  expect(out).toMatch(/^light .*muted on surface .*FAIL/m);
});

test("negative control: a dark-side token that drops below 4.5:1 fails the script", () => {
  const { code, out } = run(variant((css) => css.replace(/(--muted: light-dark\(#52525b, )#a1a1aa/, "$1#3f3f46")));
  expect(code).toBe(1);
  expect(out).toMatch(/^dark .*muted on surface .*FAIL/m);
});

test("a token not written as light-dark(#hex, #hex) is refused, not skipped", () => {
  const { code, out } = run(variant((css) => css.replace(/--muted: light-dark\([^)]*\);/, "--muted: #52525b;")));
  expect(code).toBe(1);
  expect(out).toMatch(/parsed as light-dark/);
});

test("removing the data-theme override fails the script", () => {
  const { code, out } = run(variant((css) => css.replace(':root[data-theme="dark"]', ':root[data-x="dark"]')));
  expect(code).toBe(1);
  expect(out).toMatch(/data-theme="dark"/);
});
