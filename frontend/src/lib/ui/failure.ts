/** Plain-language message for a failed BFF call. Never shows backend text. */
export function failureMessage(status: number, code?: string | null, retryAfter?: number | null): string {
  if (status === 429) {
    return retryAfter
      ? `Too many requests. Try again in ${retryAfter} seconds.`
      : "Too many requests. Try again in a moment.";
  }
  if (status === 503 && (code === "service_waking" || !code)) {
    return "The service is waking up. This can take up to a minute; try again shortly.";
  }
  if (status === 403) return "This request was blocked for safety. Reload the page and try again.";
  if (status >= 500) return "Something went wrong on our side. Try again in a moment.";
  return "The request could not be completed.";
}

/** Only same-site paths are valid post-login targets (no open redirect). */
export function safeNext(value: string | null | undefined, fallback = "/documents"): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return fallback;
  return value;
}

export const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;

export function uploadTooLargeMessage(bytes: number): string {
  const mb = (bytes / (1024 * 1024)).toFixed(1);
  return `This file is ${mb} MB. Uploads are limited to 4 MB for now; choose a smaller file.`;
}
