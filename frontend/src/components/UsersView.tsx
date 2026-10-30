"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { api, retryAfterSeconds } from "@/lib/api/client";
import { afterUserAdded } from "@/lib/query/invalidate";
import { ApiError, useMe, useUsers, type UserRow } from "@/lib/query/hooks";
import { failureMessage } from "@/lib/ui/failure";
import { generatePassword, passwordLengthOk, PASSWORD_MAX, PASSWORD_MIN } from "@/lib/password";
import { Notice } from "./Notice";
import { buttonClass, captionClass, cardClass, headingClass, inputClass, panelClass, titleClass } from "./ui/styles";

type Role = UserRow["role"];

const NOT_ADMIN_MESSAGE = "Only workspace admins can manage users.";
/** The users query asks for this many rows (hooks.ts); getting exactly this many means the list may be cut off. */
const USERS_LIMIT = 100;
/** Tighter cells and smaller text on phones, so all four columns fit at 390 px; the container still scrolls as a fallback. */
const CELL_X = "px-2 sm:px-4";
const LENGTH_HINT = `Use ${PASSWORD_MIN} to ${PASSWORD_MAX} characters.`;

const parse = (iso: string): Date | null => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
};
const shortDate = (iso: string): string => parse(iso)?.toLocaleDateString() ?? iso;
const fullTime = (iso: string): string => parse(iso)?.toLocaleString() ?? iso;

function addErrorMessage(status: number, retryAfter: number | null): string {
  if (status === 409) return "A user with this email already exists in this workspace.";
  if (status === 403) return NOT_ADMIN_MESSAGE;
  if (status === 422) return `Check the email address and that the password has ${PASSWORD_MIN} to ${PASSWORD_MAX} characters.`;
  return failureMessage(status, null, retryAfter);
}

export function UsersView() {
  const me = useMe();
  // Fail closed: nothing but the read-only message appears unless /auth/me confirmed admin.
  // Pending shows a loading note; failed, unknown or any other role shows the message. The backend enforces it too.
  const isAdmin = me.status === "success" && me.data.role === "admin";
  return (
    <section>
      <h1 className={`mb-4 ${titleClass}`}>Users</h1>
      {me.status === "pending" ? (
        <Notice>Checking your access…</Notice>
      ) : isAdmin ? (
        <AdminUsers />
      ) : (
        <p className="text-sm text-muted">{NOT_ADMIN_MESSAGE}</p>
      )}
    </section>
  );
}

function AdminUsers() {
  const queryClient = useQueryClient();
  const users = useUsers({ enabled: true });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("agent");
  const [password, setPassword] = useState("");
  // The generated password, held in state only to show it once; cleared on dismiss, on a successful add and on unmount.
  const [revealed, setRevealed] = useState<string | null>(null);
  const [copyNote, setCopyNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);

  useEffect(() => () => setRevealed(null), []);

  const loadMessage = !users.isError
    ? null
    : users.error instanceof ApiError
      ? failureMessage(users.error.status, null, users.error.retryAfter)
      : "Could not reach the service. Check your connection and try again.";

  function onGenerate() {
    const p = generatePassword();
    setPassword(p);
    setRevealed(p);
    setCopyNote(null);
  }

  function clearSecret() {
    setRevealed(null);
    setCopyNote(null);
  }

  async function onCopy() {
    if (!revealed) return;
    try {
      await navigator.clipboard.writeText(revealed);
      setCopyNote("Copied.");
    } catch {
      setCopyNote("Could not copy. Select the password and copy it by hand.");
    }
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setAdded(null);
    if (!passwordLengthOk(password)) {
      setError(addErrorMessage(422, null));
      return;
    }
    setBusy(true);
    try {
      const { response } = await api.POST("/users", { body: { email: email.trim(), role, password } });
      if (response.ok) {
        setAdded(`Added ${email.trim()}. Send them the password outside email.`);
        setEmail("");
        setPassword("");
        setRole("agent");
        clearSecret();
        await afterUserAdded(queryClient);
      } else {
        setError(addErrorMessage(response.status, retryAfterSeconds(response)));
      }
    } catch {
      setError("Could not reach the service. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  const rows = users.data ?? null;
  return (
    <div className="space-y-6">
      <p className={captionClass}>
        People who can sign in to this workspace. There is no password reset or deactivate action yet. Ask the workspace operator.
      </p>
      <form onSubmit={onSubmit} aria-label="Add a user" className={`space-y-4 ${cardClass}`}>
        <h2 className={headingClass}>Add a user</h2>
        <label className="block text-sm">
          Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" className={`mt-1 w-full ${inputClass}`} />
        </label>
        <label className="block text-sm">
          Role
          <select value={role} onChange={(e) => setRole(e.target.value as Role)} className={`mt-1 w-full ${inputClass}`}>
            <option value="admin">Admin</option>
            <option value="agent">Agent</option>
            <option value="viewer">Viewer (read-only)</option>
          </select>
        </label>
        <div>
          <label className="block text-sm">
            Password
            <input
              type="password"
              required
              minLength={PASSWORD_MIN}
              maxLength={PASSWORD_MAX}
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                clearSecret();
              }}
              autoComplete="new-password"
              aria-describedby="password-help"
              className={`mt-1 w-full ${inputClass}`}
            />
          </label>
          <p id="password-help" className={`mt-1 ${captionClass}`}>{LENGTH_HINT} Share it outside email.</p>
          <button type="button" onClick={onGenerate} className={`mt-2 ${buttonClass({ variant: "secondary" })}`}>
            Generate password
          </button>
        </div>
        {revealed && (
          <div role="group" aria-label="Generated password" className="rounded-md border border-line p-3 text-sm">
            <p className={captionClass}>Shown once. It is not stored; copy it now.</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <code className="break-all font-mono">{revealed}</code>
              <button type="button" onClick={() => void onCopy()} className={buttonClass({ variant: "secondary" })}>
                Copy
              </button>
              <button type="button" onClick={clearSecret} className={buttonClass({ variant: "ghost" })}>
                Hide
              </button>
            </div>
            {copyNote && <p role="status" className={`mt-2 ${captionClass}`}>{copyNote}</p>}
          </div>
        )}
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        {added && <p role="status" className="text-sm">{added}</p>}
        <button type="submit" disabled={busy} className={buttonClass({ variant: "primary" })}>
          {busy ? "Adding…" : "Add user"}
        </button>
      </form>

      {loadMessage && (
        <div>
          <p role="alert" className="mb-2 text-sm text-danger">{loadMessage}</p>
          <button type="button" className={buttonClass({ variant: "secondary" })} onClick={() => void users.refetch()}>
            Try again
          </button>
        </div>
      )}
      {rows === null ? (
        !loadMessage && <Notice>Loading users…</Notice>
      ) : (
        <div>
          <p className={`mb-2 ${captionClass}`}>
            {rows.length === 1 ? "1 user" : `${rows.length} users`}
            {rows.length === USERS_LIMIT && ". Showing the first 100 users."}
          </p>
          {/* The table scrolls inside its own container on narrow screens; long emails truncate. */}
          <div className={`overflow-x-auto ${panelClass}`}>
            <table className="w-full text-left text-xs sm:text-sm">
              <caption className="sr-only">Users in this workspace</caption>
              <thead className="border-b border-line text-muted">
                <tr>
                  <th scope="col" className={`${CELL_X} py-2 font-medium`}>Email</th>
                  <th scope="col" className={`${CELL_X} py-2 font-medium`}>Role</th>
                  <th scope="col" className={`${CELL_X} py-2 font-medium`}>Status</th>
                  <th scope="col" className={`${CELL_X} py-2 font-medium`}>Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((u) => (
                  <tr key={u.id}>
                    <td title={u.email} className={`max-w-[7rem] truncate ${CELL_X} py-3 sm:max-w-xs`}>{u.email}</td>
                    <td className={`${CELL_X} py-3`}>{u.role}</td>
                    <td className={`${CELL_X} py-3`}>{u.is_active ? "Active" : "Inactive"}</td>
                    <td title={fullTime(u.created_at)} className={`whitespace-nowrap ${CELL_X} py-3`}>{shortDate(u.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
