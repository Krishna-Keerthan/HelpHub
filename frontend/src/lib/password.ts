export const PASSWORD_MIN = 12;
export const PASSWORD_MAX = 128;
export const GENERATED_LENGTH = 16;

export const GENERATED_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789-_@#%+=";

/** Random password from the CSPRNG. Rejection sampling keeps every character equally likely. */
export function generatePassword(length: number = GENERATED_LENGTH): string {
  const n = GENERATED_ALPHABET.length;
  const limit = 256 - (256 % n);
  let out = "";
  while (out.length < length) {
    const bytes = crypto.getRandomValues(new Uint8Array(length));
    for (const b of bytes) {
      if (b < limit && out.length < length) out += GENERATED_ALPHABET[b % n];
    }
  }
  return out;
}

export const passwordLengthOk = (p: string) => p.length >= PASSWORD_MIN && p.length <= PASSWORD_MAX;
