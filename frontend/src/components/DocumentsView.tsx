"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Notice } from "./Notice";
import { failureMessage, MAX_UPLOAD_BYTES, uploadTooLargeMessage } from "@/lib/ui/failure";

type Doc = components["schemas"]["DocumentRead"];
const POLL_MS = 4000;

function retryAfter(res: Response): number | null {
  const n = Number(res.headers.get("Retry-After"));
  return n > 0 ? n : null;
}

export function DocumentsView() {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
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
      const { response } = await api.POST("/documents/upload", {
        body: { file: "" },
        bodySerializer: () => form,
      });
      if (response.ok) await load();
      else if (response.status === 413) setMessage("The server rejected this file as too large.");
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
        <button type="button" className="min-h-10 px-1 text-sm underline" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      <p id="upload-hint" className="mb-3 text-xs text-muted">Files up to 4 MB.</p>
      {message && (
        <p role="alert" className="mb-3 text-sm text-danger">
          {message}
        </p>
      )}
      {loadFailed && (
        <button type="button" className="mb-3 min-h-10 rounded border border-line px-3 text-sm" onClick={() => void load()}>
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
              <button
                type="button"
                aria-label={`Delete ${d.title}`}
                className="min-h-10 px-1 text-sm text-danger underline"
                onClick={() => void onDelete(d)}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
