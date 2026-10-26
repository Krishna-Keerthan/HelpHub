"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Notice } from "./Notice";
import { failureMessage, MAX_UPLOAD_BYTES, uploadTooLargeMessage } from "@/lib/ui/failure";

type Doc = components["schemas"]["DocumentRead"];
const POLL_MS = 4000;

const READ_ONLY_MESSAGE = "This account is read-only, so it cannot upload documents.";

function retryAfter(res: Response): number | null {
  const n = Number(res.headers.get("Retry-After"));
  return n > 0 ? n : null;
}

// The backend's 413 detail says which limit was hit (file, request body or extracted text); show it.
function tooLargeMessage(error: unknown): string {
  const detail = typeof (error as { detail?: unknown } | undefined)?.detail === "string" ? (error as { detail: string }).detail : null;
  const cap = "Documents are limited to 4 MB and about 500,000 extracted characters.";
  return detail ? `The server rejected this file: ${detail}. ${cap}` : `The server rejected this file as too large. ${cap}`;
}

export function DocumentsView() {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  // Write controls need a positive answer: until /auth/me confirms admin or agent, the view is read-only.
  const [access, setAccess] = useState<"checking" | "writer" | "readonly">("checking");
  const canWrite = access === "writer";
  const readOnly = access === "readonly";
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const { data, response } = await api.GET("/documents");
      if (data) {
        setDocs(data);
        setMessage(null);
        setLoadFailed(false);
      } else {
        setLoadFailed(true);
        setMessage(failureMessage(response.status, null, retryAfter(response)));
      }
    } catch {
      setLoadFailed(true);
      setMessage("Could not reach the service. Check your connection and try again.");
    }
  }, []);

  useEffect(() => {
    // Initial fetch on mount; setState happens after the awaited request, not synchronously.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  useEffect(() => {
    // Fail closed: a failed or unparseable lookup, or any role other than admin/agent, stays read-only.
    // The backend still enforces; this only decides what is shown.
    void (async () => {
      try {
        const { data } = await api.GET("/auth/me");
        const role = (data as { role?: unknown } | undefined)?.role;
        setAccess(role === "admin" || role === "agent" ? "writer" : "readonly");
      } catch {
        setAccess("readonly");
      }
    })();
  }, []);

  const hasPending = docs?.some((d) => d.status === "PENDING") ?? false;
  useEffect(() => {
    if (!hasPending) return;
    const t = setTimeout(() => void load(), POLL_MS);
    return () => clearTimeout(t);
  }, [hasPending, docs, load]);

  async function onUpload(file: File) {
    if (file.size > MAX_UPLOAD_BYTES) {
      setMessage(uploadTooLargeMessage(file.size));
      return;
    }
    setUploading(true);
    setMessage(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const { response, error } = await api.POST("/documents/upload", {
        body: { file: "" },
        bodySerializer: () => form,
      });
      if (response.ok) await load();
      else if (response.status === 403) setMessage(READ_ONLY_MESSAGE);
      else if (response.status === 413) setMessage(tooLargeMessage(error));
      else if (response.status === 415) setMessage("This file type is not supported.");
      else setMessage(failureMessage(response.status, null, retryAfter(response)));
    } catch {
      setMessage("Upload failed. Check your connection and try again.");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function onDelete(doc: Doc) {
    if (!window.confirm(`Delete "${doc.title}"? This cannot be undone.`)) return;
    try {
      const { response } = await api.DELETE("/documents/{document_id}", {
        params: { path: { document_id: doc.id } },
      });
      if (response.ok) setDocs((cur) => cur?.filter((d) => d.id !== doc.id) ?? null);
      else setMessage(failureMessage(response.status, null, retryAfter(response)));
    } catch {
      setMessage("Delete failed. Check your connection and try again.");
    }
  }

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Documents</h1>
        {readOnly && <span className="ml-auto text-sm text-muted">Read-only account: uploads are disabled.</span>}
        {canWrite && (
        <label className="ml-auto inline-flex min-h-10 cursor-pointer items-center rounded bg-accent px-3 text-sm text-accent-fg focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent">
          {uploading ? "Uploading…" : "Upload"}
          <input
            ref={fileInput}
            type="file"
            aria-label="Upload a document"
            aria-describedby="upload-hint"
            className="sr-only"
            disabled={uploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void onUpload(file);
            }}
          />
        </label>
        )}
        <button type="button" className={`min-h-10 px-1 text-sm underline${canWrite ? "" : " ml-3"}`} onClick={() => void load()}>
          Refresh
        </button>
      </div>
      {canWrite && (
        <p id="upload-hint" className="mb-3 text-xs text-muted">Files up to 4 MB. Plain-text documents are also capped at about 500,000 extracted characters.</p>
      )}
      {message && (
        <p role="alert" className="mb-3 text-sm text-danger">
          {message}
        </p>
      )}
      {loadFailed && (
        <button type="button" className="mb-3 min-h-10 rounded border border-control-border px-3 text-sm" onClick={() => void load()}>
          Try again
        </button>
      )}
      {docs === null ? (
        !message && <Notice className="rounded">Loading documents…</Notice>
      ) : docs.length === 0 ? (
        <div className="rounded border border-dashed border-line p-6 text-center">
          <p>No documents yet.</p>
          <p className="mt-1 text-sm text-muted">Upload a file up to 4 MB and it becomes searchable in chat.</p>
        </div>
      ) : (
        <ul aria-label="Documents" className="divide-y divide-line">
          {docs.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <span className="min-w-0 flex-1 basis-40 truncate">{d.title}</span>
              <span className="text-xs text-muted">{d.status}</span>
              {canWrite && (
                <button
                  type="button"
                  aria-label={`Delete ${d.title}`}
                  className="min-h-10 px-1 text-sm text-danger underline"
                  onClick={() => void onDelete(d)}
                >
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
