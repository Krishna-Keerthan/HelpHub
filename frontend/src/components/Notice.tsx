/**
 * Informational message announced politely (waking up, searching, loading).
 * Messages that block the user's action (login/upload/chat errors) use role="alert" instead.
 */
/** Rounded by default; `square` is for the full-width banner at the top of a page. */
export function Notice({ children, className = "", square = false }: { children: React.ReactNode; className?: string; square?: boolean }) {
  return (
    <div role="status" aria-live="polite" className={`bg-info px-4 py-2 text-sm text-info-fg ${square ? "" : "rounded-md"} ${className}`}>
      {children}
    </div>
  );
}
