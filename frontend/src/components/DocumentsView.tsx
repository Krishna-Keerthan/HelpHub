"use client";

import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, retryAfterSeconds } from "@/lib/api/client";
import { afterDocumentsChanged } from "@/lib/query/invalidate";
import { ApiError, queryKeys, useDocuments, useMe, type Doc, type DocumentsPage } from "@/lib/query/hooks";
import { Notice } from "./Notice";
import { Pagination } from "./ui/Pagination";
import { StatusPill } from "./ui/StatusPill";
import { buttonClass, captionClass, emptyClass, panelClass, titleClass } from "./ui/styles";
import { failureMessage, MAX_UPLOAD_BYTES, uploadTooLargeMessage } from "@/lib/ui/failure";
import { clampedPage, pagingQuery, parsePaging } from "@/lib/ui/paging";


const READ_ONLY_MESSAGE = "This account is read-only, so it cannot upload documents.";

// The backend's 413 detail says which limit was hit (file, request body or extracted text); show it.
function tooLargeMessage(error: unknown): string {
  const detail = typeof (error as { detail?: unknown } | undefined)?.detail === "string" ? (error as { detail: string }).detail : null;
  const cap = "Documents are limited to 4 MB and about 500,000 extracted characters.";
  return detail ? `The server rejected this file: ${detail}. ${cap}` : `The server rejected this file as too large. ${cap}`;
}

export function DocumentsView() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  // The page and page size live in the URL (?page=2&size=25) so reload, back and shared links keep them.
  const { page, size } = parsePaging(useSearchParams() ?? new URLSearchParams());
  const documents = useDocuments({ page, size });
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

  const docs = documents.data?.items ?? null;
  const total = documents.data?.total ?? null;
  const goTo = (nextPage: number, nextSize: number, replace = false) => {
    const url = `${pathname}${pagingQuery(nextPage, nextSize)}`;
    if (replace) router.replace(url, { scroll: false });
    else router.push(url, { scroll: false });
  };

  // A page past the end (rows deleted, a typed URL) moves to the last page, or back one page when no total is known.
  // Only acts on settled data, never on a cached answer that is still being revalidated.
  const settledData = documents.data && !documents.isFetching ? documents.data : null;
  const target = settledData ? clampedPage(page, size, settledData.total, settledData.items.length) : page;
  useEffect(() => {
    if (target !== page) router.replace(`${pathname}${pagingQuery(target, size)}`, { scroll: false });
  }, [target, page, size, pathname, router]);
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
        await afterDocumentsChanged(queryClient);
      }
      else if (response.status === 403) setActionMessage(READ_ONLY_MESSAGE);
      else if (response.status === 413) setActionMessage(tooLargeMessage(error));
      else if (response.status === 415) setActionMessage("This file type is not supported.");
      else setActionMessage(failureMessage(response.status, null, retryAfterSeconds(response)));
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
        // Drop the row (and one from the total) from every cached page that held it, then refetch.
        queryClient.setQueriesData<DocumentsPage>({ queryKey: [...queryKeys.documents, "list"] }, (cur) =>
          cur?.items.some((d) => d.id === doc.id)
            ? { items: cur.items.filter((d) => d.id !== doc.id), total: cur.total === null ? null : Math.max(0, cur.total - 1) }
            : cur,
        );
        await afterDocumentsChanged(queryClient);
      } else setActionMessage(failureMessage(response.status, null, retryAfterSeconds(response)));
    } catch {
      setActionMessage("Delete failed. Check your connection and try again.");
    }
  }

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="mr-auto">
          <h1 className={titleClass}>Documents</h1>
          <p className="mt-1 text-sm text-muted">The files your chat answers are built from.</p>
        </div>
        {readOnly && <span className="order-last basis-full text-sm text-muted">Read-only account: uploads are disabled.</span>}
        {canWrite && (
        <label className={buttonClass({ variant: "primary", label: true })}>
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
        <button type="button" className={buttonClass({ variant: "ghost" })} onClick={reload}>
          Refresh
        </button>
      </div>
      {canWrite && (
        <p id="upload-hint" className={`mb-3 ${captionClass}`}>Files up to 4 MB. Plain-text documents are also capped at about 500,000 extracted characters.</p>
      )}
      {message && (
        <p role="alert" className="mb-3 text-sm text-danger">
          {message}
        </p>
      )}
      {loadFailed && (
        <button type="button" className={`mb-3 ${buttonClass({ variant: "secondary" })}`} onClick={reload}>
          Try again
        </button>
      )}
      {docs === null ? (
        !message && <Notice>Loading documents…</Notice>
      ) : docs.length === 0 && page > 1 ? (
        <Notice>No documents on this page.</Notice>
      ) : docs.length === 0 ? (
        <div className={`${emptyClass} text-center`}>
          <p>No documents yet.</p>
          <p className="mt-1 text-sm text-muted">Upload a file up to 4 MB and it becomes searchable in chat.</p>
        </div>
      ) : (
        <ul aria-label="Documents" className={`divide-y divide-line px-4 ${panelClass}`}>
          {docs.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-3">
              <span className="min-w-0 flex-1 basis-40 truncate">{d.title}</span>
              <StatusPill status={d.status} />
              {canDelete && (
                <button
                  type="button"
                  aria-label={`Delete ${d.title}`}
                  className={buttonClass({ variant: "danger" })}
                  onClick={() => void onDelete(d)}
                >
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {docs !== null && (docs.length > 0 || page > 1) && (
        <Pagination
          page={page}
          size={size}
          count={docs.length}
          total={total}
          onPage={(p) => goTo(p, size)}
          onSize={(n) => goTo(1, n)}
        />
      )}
    </section>
  );
}
