/**
 * Informational message announced politely (waking up, searching, loading).
 * Messages that block the user's action (login/upload/chat errors) use role="alert" instead.
 */
export function Notice({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div role="status" aria-live="polite" className={`bg-info px-4 py-2 text-sm text-info-fg ${className}`}>
      {children}
    </div>
  );
}
