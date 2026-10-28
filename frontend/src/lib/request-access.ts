export const ACCESS_SUBJECT = "HelpHub access request";

const BODY = [
  "Workspace name:",
  "Workspace slug (lowercase letters, digits, hyphens):",
  "Admin email:",
  "",
  "Never send a password. Credentials are shared separately, outside email.",
].join("\n");

/** mailto link for the closed-beta access request, or null when no contact address is configured. */
export function requestAccessHref(contactEmail: string | undefined): string | null {
  const to = contactEmail?.trim();
  if (!to) return null;
  return `mailto:${encodeURIComponent(to).replace(/%40/g, "@")}?subject=${encodeURIComponent(ACCESS_SUBJECT)}&body=${encodeURIComponent(BODY)}`;
}

/** Plain mailto link to the contact address, or null when it is not configured. */
export function contactHref(contactEmail: string | undefined): string | null {
  const to = contactEmail?.trim();
  return to ? `mailto:${encodeURIComponent(to).replace(/%40/g, "@")}` : null;
}
