# Accepted risks

Read by every reviewer agent. Do not report an entry unless its **Condition** changed or its **Revisit when** trigger has been reached. Delete entries when resolved. IDs are stable; never reuse one.

| ID | Risk | Why accepted / condition that must stay true | Revisit when |
|---|---|---|---|
| AR-01 | PDF extraction is resource-limited (child process, timeout, CPU/memory rlimits), not isolated | Limits bound the damage; no network or fs sandbox yet. Stays true while extraction runs only in `services/pdf_worker.py` | Docker hardening (Day 12) |
| AR-02 | Document ingestion runs inline in the request | Fine at current volume. Stays true while uploads are size-capped | Worker lands (Day 8) |
| AR-03 | Re-posted PENDING documents repeat embedding work | Wasted compute only; no data effect | Worker lands (Day 8) |
| AR-04 | Elasticsearch security disabled in dev compose | Bound to 127.0.0.1, dev data only. Stays true while compose binds localhost | Deploy |
| AR-05 | `tenants` table has no RLS, by design | It is the lookup used for login and registration; touched only via `repositories/tenants.py` and `services/auth.py`, never joined to tenant data | Never, unless tenants gain tenant-owned columns |
| AR-06 | Reindex race: a document written during reindex may be indexed stale | Nothing leaks: search hydrates from Postgres with `tenant_id` + RLS and drops missing or foreign ids | Search consistency work |
| AR-07 | No login rate limiting | Argon2 cost and the dummy-hash path only | Before public deploy (Day 12) |
| AR-08 | No refresh tokens; access tokens live `ACCESS_TOKEN_MINUTES` | Short-lived token, no revocation list | Before public deploy (Day 12) |
| AR-09 | Failed or interrupted assistant rows keep partial text | Text stays inside the owning tenant; status marks it incomplete | Chat UI work |
| AR-10 | Retrieval threshold is provisional | Tuned by hand on a tiny corpus | Day 6 eval |
| AR-11 | BM25 and vector scores are not comparable | They are never merged or thresholded together; each endpoint returns its own raw score | Hybrid search |
| AR-12 | Untenanted `get_session` in `GET /health/db` | Connectivity check only; queries no tenant table, returns no row data | Before public deploy |
| AR-13 | `delete_document_chunks` refreshes the whole alias on every delete; there is no rate limiting on `/search`, `/search/keyword`, `/search/hybrid` and `/chat/stream` | Latency only, no data effect; one dev node | Before public deploy (Day 12) |
| AR-14 | Migration 0007 added `ck_documents_search_index_status` as a normal (validated) CHECK, not `NOT VALID` | At this size the full-table validation under a heavy lock is instant. Stays true while `documents` is small | Validate before the first migration on a populated production table: add the constraint `NOT VALID`, then `VALIDATE CONSTRAINT` separately |
| AR-15 | ANN recall for outlier tenants is probabilistic (random HNSW levels/pruning), independent of vacuuming | The exact fallback is the correctness mechanism; tests asserting `used_fallback` False are conditioned on a reachability probe (`tests/isolation/ann_helpers.py`) | If the fallback rate in production metrics exceeds a small fraction, consider per-tenant partitioning |
| AR-16 | `app.api.deps` imports sqlalchemy (import-linter ignore) | Only for the `TenantSession` type alias; no queries in `api/` | Day 12 (re-export the type from `app.db`, drop the ignore) |
| AR-17 | `guard_bash` is best-effort, not a security boundary (python heredocs are not inspected) | It stops accidents, not a determined actor; the permission mode is the real control | Never; do not rely on it for isolation |
