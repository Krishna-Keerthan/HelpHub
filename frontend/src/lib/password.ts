export const PASSWORD_MIN = 12;
export const PASSWORD_MAX = 128;
export const GENERATED_LENGTH = 16;

export const PASSWORD_CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789-_@#%+=";

/** Random password from the CSPRNG. Rejection sampling keeps every character equally likely. */
export function generatePassword(length: number = GENERATED_LENGTH): string {
  const n = PASSWORD_CHARSET.length;
  const limit = 256 - (256 % n);
  let out = "";
  while (out.length < length) {
    const bytes = crypto.getRandomValues(new Uint8Array(length));
    for (const b of bytes) {
      if (b < limit && out.length < length) out += PASSWORD_CHARSET[b % n];
    }
  }
  return out;
}

export const passwordLengthOk = (p: string) => p.length >= PASSWORD_MIN && p.length <= PASSWORD_MAX;
