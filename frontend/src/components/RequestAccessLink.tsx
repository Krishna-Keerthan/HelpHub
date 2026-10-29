import { buttonClass } from "@/components/ui/styles";
import { requestAccessHref } from "@/lib/request-access";

/** Renders nothing when NEXT_PUBLIC_CONTACT_EMAIL is not set. */
export function RequestAccessLink({ contactEmail }: { contactEmail: string | undefined }) {
  const href = requestAccessHref(contactEmail);
  if (!href) return null;
  return (
    <a href={href} className={buttonClass({ variant: "ghost" })}>
      Request access
    </a>
  );
}
