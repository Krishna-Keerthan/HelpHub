"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "@/lib/api/client";
import { ApiError, queryKeys, useDocuments, useMe, type Doc } from "@/lib/query/hooks";
import { Notice } from "./Notice";
import { failureMessage, MAX_UPLOAD_BYTES, uploadTooLargeMessage } from "@/lib/ui/failure";


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
  const queryClient = useQueryClient();
  const documents = useDocuments();
  const me = useMe();
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // Fail closed: write controls need a successful, parseable /auth/me answering a role that may use
  // them. Pending, failed (including a failed revalidation of an earlier answer) or unknown means read-only.
  // The backend still enforces roles; this only decides what is shown.
  const role = me.status === "success" ? me.data.role : null;
  const settled = me.status !== "pending";
  const canWrite = role === "admin" || role === "agent"; // Upload: admin and agent
  const canDelete = role === "admin"; // Delete: admin only (the backend uses require_admin)
  const readOnly = settled && !canWrite;

  const docs = documents.data ?? null;
  const loadFailed = documents.isError;
  // A failed revalidation keeps the last list on screen, and says so.
  const loadMessage = !loadFailed
    ? null
    : (documents.error instanceof ApiError
        ? failureMessage(documents.error.status, null, documents.error.retryAfter)
        : "Could not reach the service. Check your connection and try again.") +
      (docs ? " Showing the last list that loaded." : "");
  const message = actionMessage ?? loadMessage;

  const reload = () => {
    setActionMessage(null);
    void documents.refetch();
  };

  async function onUpload(file: File) {
    if (file.size > MAX_UPLOAD_BYTES) {
      setActionMessage(uploadTooLargeMessage(file.size));
      return;
    }
    setUploading(true);
    setActionMessage(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const { response, error } = await api.POST("/documents/upload", {
        body: { file: "" },
        bodySerializer: () => form,
      });
      if (response.ok) {
        setActionMessage(null);
        await queryClient.invalidateQueries({ queryKey: queryKeys.documents });
      }
      else if (response.status === 403) setActionMessage(READ_ONLY_MESSAGE);
      else if (response.status === 413) setActionMessage(tooLargeMessage(error));
      else if (response.status === 415) setActionMessage("This file type is not supported.");
      else setActionMessage(failureMessage(response.status, null, retryAfter(response)));
    } catch {
      setActionMessage("Upload failed. Check your connection and try again.");
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
      if (response.ok) {
        queryClient.setQueryData<Doc[]>(queryKeys.documents, (cur) => cur?.filter((d) => d.id !== doc.id));
        await queryClient.invalidateQueries({ queryKey: queryKeys.documents });
      } else setActionMessage(failureMessage(response.status, null, retryAfter(response)));
    } catch {
      setActionMessage("Delete failed. Check your connection and try again.");
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
        <button type="button" className={`min-h-10 px-1 text-sm underline${canWrite ? "" : " ml-3"}`} onClick={reload}>
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
        <button type="button" className="mb-3 min-h-10 rounded border border-control-border px-3 text-sm" onClick={reload}>
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
              {canDelete && (
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
