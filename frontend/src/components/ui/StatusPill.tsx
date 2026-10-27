const PILL_BASE = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium";

const TONES: Record<string, string> = {
  READY: "bg-ok-bg text-ok",
  PENDING: "bg-warn-bg text-warn",
  FAILED: "bg-bad-bg text-bad",
};

/** Document status as a pill. The text is the status itself; an unknown status gets the neutral tone. */
export function StatusPill({ status }: { status: string }) {
  return <span className={`${PILL_BASE} ${TONES[status] ?? "bg-chip text-muted"}`}>{status}</span>;
}
