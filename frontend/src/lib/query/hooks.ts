"use client";

import { useQuery } from "@tanstack/react-query";
import { api, retryAfterSeconds } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { DOCUMENTS_STALE_MS, ME_STALE_MS } from "./client";

export type Doc = components["schemas"]["DocumentRead"];

export const queryKeys = {
  documents: ["documents"] as const,
  me: ["me"] as const,
};

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

/** GET /documents, shared by Documents and the chat citation chips. */
export function useDocuments({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.documents,
    enabled,
    staleTime: DOCUMENTS_STALE_MS,
    queryFn: async (): Promise<Doc[]> => {
      const { data, response } = await api.GET("/documents");
      if (!data) throw new ApiError(response.status, retryAfterSeconds(response));
      return data;
    },
    // Documents being processed finish on their own; poll until none is pending.
    refetchInterval: (q) => (q.state.data?.some((d) => d.status === "PENDING") ? POLL_MS : false),
  });
}

/** GET /auth/me. Anything that is not a clear answer with a string role is an error (fail closed). */
export function useMe() {
  return useQuery({
    queryKey: queryKeys.me,
    staleTime: ME_STALE_MS,
    queryFn: async (): Promise<{ role: string }> => {
      const { data, response } = await api.GET("/auth/me");
      const role = (data as { role?: unknown } | undefined)?.role;
      if (!data) throw new ApiError(response.status, retryAfterSeconds(response));
      if (typeof role !== "string") throw new ApiError(response.status, null);
      return { role };
    },
  });
}
