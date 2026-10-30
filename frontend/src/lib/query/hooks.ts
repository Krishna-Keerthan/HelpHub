"use client";

import { useQuery } from "@tanstack/react-query";
import { api, retryAfterSeconds } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { DOCUMENTS_STALE_MS, ME_STALE_MS } from "./client";

export type Doc = components["schemas"]["DocumentRead"];
export type UserRow = components["schemas"]["UserRead"];

export const queryKeys = {
  /** Prefix of every documents entry (pages and single documents): invalidating it hits them all. */
  documents: ["documents"] as const,
  documentsPage: (page: number, size: number) => ["documents", "list", page, size] as const,
  document: (id: string) => ["documents", "one", id] as const,
  me: ["me"] as const,
  users: ["users"] as const,
  conversation: (id: string) => ["conversation", id] as const,
};

/** The server returns at most this many messages per read; a longer conversation shows its first ones (D15). */
export const HISTORY_LIMIT = 200;

const POLL_MS = 4000;

/** A non-2xx answer. Carries only the status and Retry-After, never backend text. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly retryAfter: number | null,
  ) {
    super(`request failed with HTTP ${status}`);
  }
}

/** One page of documents and the workspace total from `X-Total-Count`; null when the header is absent or not a count. */
export type DocumentsPage = { items: Doc[]; total: number | null };

export function parseTotal(value: string | null): number | null {
  return value !== null && /^\d{1,9}$/.test(value.trim()) ? Number(value) : null;
}

/** GET /documents for one page. Every page is its own cache entry under the `["documents"]` prefix. */
export function useDocuments({ page, size }: { page: number; size: number }) {
  return useQuery({
    queryKey: queryKeys.documentsPage(page, size),
    staleTime: DOCUMENTS_STALE_MS,
    queryFn: async (): Promise<DocumentsPage> => {
      const { data, response } = await api.GET("/documents", { params: { query: { limit: size, offset: (page - 1) * size } } });
      if (!data) throw new ApiError(response.status, retryAfterSeconds(response));
      return { items: data, total: parseTotal(response.headers.get("x-total-count")) };
    },
    // Documents being processed finish on their own; poll while the visible page has a pending one.
    refetchInterval: (q) => (q.state.data?.items.some((d) => d.status === "PENDING") ? POLL_MS : false),
  });
}

/**
 * GET /documents/{id}, used when a citation chip is opened. A 404 is a clear answer (`exists: false`);
 * any other failure is an error, so nothing is claimed about the document.
 */
export function useDocumentExists(id: string, { enabled }: { enabled: boolean }) {
  return useQuery({
    queryKey: queryKeys.document(id),
    enabled,
    staleTime: DOCUMENTS_STALE_MS,
    queryFn: async (): Promise<{ exists: boolean }> => {
      const { data, response } = await api.GET("/documents/{document_id}", { params: { path: { document_id: id } } });
      if (response.status === 404) return { exists: false };
      if (!data) throw new ApiError(response.status, retryAfterSeconds(response));
      return { exists: true };
    },
  });
}

/** GET /auth/me. Anything that is not a clear answer with a string role is an error (fail closed). */
export function useMe() {
  return useQuery({
    queryKey: queryKeys.me,
    staleTime: ME_STALE_MS,
    queryFn: async (): Promise<{ role: string; email: string | null }> => {
      const { data, response } = await api.GET("/auth/me");
      const { role, email } = (data ?? {}) as { role?: unknown; email?: unknown };
      if (!data) throw new ApiError(response.status, retryAfterSeconds(response));
      if (typeof role !== "string") throw new ApiError(response.status, null);
      return { role, email: typeof email === "string" ? email : null };
    },
  });
}

/**
 * GET /conversations/{id}/messages for a chat that is being restored. Always refetched on mount: the server
 * is the source of truth until the page hydrates once; after that local state is authoritative.
 */
export function useConversationMessages(id: string | null) {
  return useQuery({
    queryKey: queryKeys.conversation(id ?? ""),
    enabled: id !== null,
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const { data, response } = await api.GET("/conversations/{conversation_id}/messages", {
        params: { path: { conversation_id: id! }, query: { limit: HISTORY_LIMIT } },
      });
      if (!data) throw new ApiError(response.status, retryAfterSeconds(response));
      return data;
    },
  });
}

/** GET /users (admin page only; the first 100 users, the server maximum). */
export function useUsers({ enabled }: { enabled: boolean }) {
  return useQuery({
    queryKey: queryKeys.users,
    enabled,
    staleTime: 0,
    queryFn: async (): Promise<UserRow[]> => {
      const { data, response } = await api.GET("/users", { params: { query: { limit: 100 } } });
      if (!data) throw new ApiError(response.status, retryAfterSeconds(response));
      return data;
    },
  });
}
