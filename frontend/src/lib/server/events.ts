export type CountedEvent = "refresh_indeterminate" | "forced_logout";

const counts = new Map<string, number>();

/**
 * Count an auth event and log one structured line. `reason` is a fixed label, never a
 * token, body or error message. The count is per server instance (serverless), so the
 * aggregate comes from summing these log lines, not from the number in them.
 */
export function countEvent(event: CountedEvent, reason: string): void {
  const key = `${event}:${reason}`;
  const n = (counts.get(key) ?? 0) + 1;
  counts.set(key, n);
  console.info(JSON.stringify({ metric: event, reason, instance_count: n }));
}

export function eventCount(event: CountedEvent, reason: string): number {
  return counts.get(`${event}:${reason}`) ?? 0;
}
