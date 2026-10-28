import { expect, test, vi } from "vitest";
import { generatePassword, GENERATED_LENGTH, GENERATED_ALPHABET, passwordLengthOk } from "./password";

test("is 16 characters from the charset only", () => {
  for (let i = 0; i < 200; i++) {
    const p = generatePassword();
    expect(p).toHaveLength(16);
    expect(GENERATED_LENGTH).toBe(16);
    for (const c of p) expect(GENERATED_ALPHABET).toContain(c);
  }
});

test("uses crypto.getRandomValues and differs between calls", () => {
  const spy = vi.spyOn(crypto, "getRandomValues");
  const a = generatePassword();
  expect(spy).toHaveBeenCalled();
  expect(generatePassword()).not.toBe(a);
  spy.mockRestore();
});

test("rejects bytes that would bias the choice", () => {
  const n = GENERATED_ALPHABET.length;
  const limit = 256 - (256 % n);
  let first = true;
  const spy = vi.spyOn(crypto, "getRandomValues").mockImplementation(((a: Uint8Array) => {
    a.fill(first ? limit : 0); // first batch is all out of range, then index 0
    first = false;
    return a;
  }) as typeof crypto.getRandomValues);
  expect(generatePassword(4)).toBe(GENERATED_ALPHABET[0]!.repeat(4));
  spy.mockRestore();
});

test("length check is 12 to 128", () => {
  expect(passwordLengthOk("a".repeat(11))).toBe(false);
  expect(passwordLengthOk("a".repeat(12))).toBe(true);
  expect(passwordLengthOk("a".repeat(128))).toBe(true);
  expect(passwordLengthOk("a".repeat(129))).toBe(false);
});
