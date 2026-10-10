# Day 3 plan: documents + chunks + embeddings + vector search (final, with your amendments)

## Context
Day 2 is done (auth, users, RLS on `users`, `tenant_transaction`, migration head 0003). Day 3 adds the knowledge-base core; your six test files are the spec. Rules: no weakened/skipped/xfailed assertion; after commit 0 existing tests are not edited again (new tests only); every assertion-level change is listed per commit; no repo-wide `ruff format` (format only touched files).
Step zero of implementation: copy this plan to `docs/plans/day-03.md` and commit it. Then one commit at a time, stop and report after each.

## Verified facts
- pgvector extension installed = **0.8.7** (image `pgvector/pgvector:pg16`, PG 16.15); >= 0.8.0, `hnsw.iterative_scan` available. Extension created in migration 0001. `helphub_app` gets DML on new owner tables via default privileges; RLS not forced (owner bypasses).
- Context7 unavailable; used pgvector-python README + upstream `tests/test_sqlalchemy.py` and `sqlalchemy/vector.py`.
- **`register_vector` is not needed** for ORM/Core `Vector(384)` columns: the type's bind processor sends text `'[..]'` and the result processor parses it; upstream tests a plain asyncpg engine. It is only needed for raw Python lists bound without the type. Decision: no codec registration anywhere; raw-SQL tests bind with `bindparam("vec", type_=Vector(384))`.
- `pgvector`, `fastembed`, `pypdf` are in pyproject/uv.lock but not installed yet (`uv sync`).

## Schema (migration 0004)
- `documents`: `id`, `tenant_id` (FK tenants CASCADE), `title`, `raw_text`, `content_hash` **NOT NULL**, `status` (default `PENDING`, CHECK PENDING/READY/FAILED), `error` NULL, `created_by` (+ composite FK `(tenant_id, created_by) -> users(tenant_id, id)` NO ACTION; if time is short defer to a later migration and tell you), `created_at`, `updated_at`. `UNIQUE(tenant_id, id)`; **named** `UNIQUE(tenant_id, content_hash)`.
- `chunks`: `id`, `tenant_id`, `document_id`, `chunk_index`, column `text` (Python attribute `content`), `char_start` NOT NULL, `char_end` NOT NULL, CHECK `char_start >= 0 AND char_end > char_start`, `embedding vector(384)` NOT NULL, `embedding_model` NOT NULL, `created_at`. Composite FK `(tenant_id, document_id) -> documents(tenant_id, id) ON DELETE CASCADE`; `UNIQUE(document_id, chunk_index)`.
- HNSW `(m=16, ef_construction=64, vector_cosine_ops)` declared identically in model (`postgresql_using/with/ops`) and migration. If `alembic check` cannot be made clean, report it; no broad suppression.
- RLS enabled + `tenant_isolation` policy (same `NULLIF(current_setting('app.tenant_id', true), '')::uuid` USING + WITH CHECK as 0003) on both tables; downgrade drops policies/indexes/tables.
- Tests omit the now-NOT-NULL columns, so they get plumbing helpers `make_document` / `make_chunk` in `conftest.py` (schema stays strict instead of being loosened).

## Commits
**0. Tests-only fixes (the only allowed edit of existing tests).** Assertion-level changes listed in the report.
- Imports/claims: `from security` -> `app.core.security`; token `sub = str(user_id)`, drop the ignored `role` claim.
- Vector binding via `bindparam("vec", type_=Vector(384))` (no fixture codec); `await owner_conn.rollback()` after each expected error.
- `test_provider_matches_db_column_dimension`: query `format_type(atttypid, atttypmod)` and assert `vector(384)` equals the provider dim.
- Cascade test counts documents and chunks = 0 after tenant delete; content-hash test asserts the constraint name; schema tests use the helpers.
- Implement the stubs: **`test_same_text_searched_isolates_tenants`, `test_limit_k_bounding`, `test_filtered_ann_with_hnsw`** (three in `test_search_isolation.py`) plus `test_ingestion_idempotency` in `test_ingestion.py`.
- `test_filtered_ann_with_hnsw` exactly as specified: owner-seeded, 200 tenant-B chunks near q, 3 tenant-A chunks far, `SET LOCAL enable_seqscan = off`, search as A with k=3 must return A's 3.
- `test_search_raw_sql_no_tenant_context` seeds a chunk first; 404 test uses real tenant-B document ids; list/detail tests seed documents so they are non-vacuous.
- Chunker coverage check compares merged source ranges (no gaps), not char counts. Register `slow` marker; real-model tests run only with `-m slow` (embedding tests that load the model get the marker; `--strict-markers` considered).
- Tests stay red until the code lands; that is expected and reported.

**1. Deps + chunker.** `uv sync`; explicit `numpy`. `chunk_text(text, max_chars, overlap)` returns `list[Chunk]`, `Chunk = TypedDict{index,start,end,text}`; paragraph, then sentence, then hard-wrap; deterministic; offsets into the original (no stripping); validates `0 <= overlap < max_chars`; empty/whitespace -> `[]`. `max_document_chars ~500000` setting.

**2. Embeddings.** `EmbeddingProvider` Protocol (`dim`, `model_name`, async `embed_passages`, async `embed_query`); `FastEmbedProvider` (bge-small-en-v1.5, `passage_embed`/`query_embed`, `asyncio.to_thread`, lazy singleton with a lock, cache dir gitignored); `FakeEmbeddingProvider` (hash-seeded, deterministic, normalised, 384-d). Sync module helpers `get_embedding` / `get_embeddings_batch` for tests only (docstring: never call from async code). `get_embedding_provider` dependency; autouse conftest override to the fake for API tests (additive). Model warm-up in lifespan. New tests: smoke test that the real dependency resolves to `FastEmbedProvider(dim 384)` without loading the model; async `embed_query` semantic test (`slow`).

**3. Migration 0004 + models** as above. Python attr `content` maps to column `text`. Verify `upgrade head; downgrade -1; upgrade head; alembic check`. New tests: RLS on both tables (`test_rls_coverage` covers them automatically), `has_table_privilege` for documents/chunks.

**4. Ingestion.** (a) `tenant_transaction`: insert document PENDING; (b) chunk + embed with no transaction open; (c) one `tenant_transaction`: bulk-insert chunks, set READY; (d) failure: separate `tenant_transaction` sets FAILED + error. Duplicate content: new = 201; existing READY = 200 (no new chunks); existing FAILED = retry on the same row. The race is resolved by catching the **named** unique constraint violation (`uq_documents_tenant_id_content_hash`), never a pre-check.

**5. Search.** `chunks_repo.vector_search`, in the same tenant transaction: `set_config('hnsw.iterative_scan','relaxed_order',true)`, `set_config('hnsw.ef_search', max(40,k) capped 1000, true)`; ANN query inside a `MATERIALIZED` CTE with explicit `tenant_id` filter (plus RLS), outer query re-sorts by distance (comment: PG17+ needs `ORDER BY distance + 0` to keep relaxed-order results re-sortable); `score = 1 - distance`; k clamped.

**6. API.** `POST /documents` accepts JSON `{title, content}`; any other Content-Type -> 415 (explicit handling, JSON path only). No existing test posts multipart to `/documents`, so uploads go to **`POST /documents/upload`** (multipart `.txt`, `.md`, `.pdf`; other types 415). Upload cap: check `Content-Length`, then bounded read. PDFs via `to_thread`, 200-page cap; encrypted/unreadable/no-text -> 422 **before** any row is created. `GET /documents` and `GET /documents/{id}` never include `raw_text`; `GET /documents/{id}/chunks` (404 across tenants); `DELETE /documents/{id}` (admin only, agent -> 403); search endpoint. Routes thin, services hold logic, SQL only in `db/`.

**7. Wrap-up.** Full `uv run pytest` (and `-m slow`), `ruff check` + format of touched files only, `alembic check`, manual two-tenant run.

## Risks
- `created_by` NO ACTION FK blocks deleting a user who created documents (tenant delete is fine: cascades hit both tables in one statement). Confirm acceptable.
- relaxed_order + `hnsw.max_scan_tuples` (20000) can return fewer than k for a small tenant among large ones.
- Alembic may not diff HNSW opclass/WITH params; pgvector `Vector` rendering in migrations.
- Model download/cache and onnxruntime memory in CI; lifespan warm-up slows startup.
- `set_config(..., true)` is lost on a mid-transaction commit; keep tenant setup and search in one transaction.
- Inline synchronous ingestion (201 READY) blocks the request on embedding; background (SAQ) later.
- Tests share the dev DB; failed cleanup leaks rows.

## Verification
`docker compose up -d`; in backend: `uv sync`, `uv run alembic upgrade head`, `downgrade -1`, `upgrade head`, `uv run alembic check`, `uv run ruff check .`, `uv run pytest`, `uv run pytest -m slow`; manual: two tenants ingest the same text, search as A returns only A's chunk ids.

## Decisions during implementation

### No `tenant_id` indexes on `documents` / `chunks` (commit 3)
- **Decision:** migration 0004 creates no btree on `tenant_id` for either table. The only chunk index is `ix_chunks_embedding_hnsw`.
- **Why:** with a `tenant_id` btree present, the planner picks "tenant btree scan + exact sort" over the HNSW index for a small tenant (the filter looks selective), so `test_filtered_ann_with_hnsw` (which asserts the HNSW index appears in the plan) fails. Without it, the only index path for the ANN `ORDER BY` is HNSW.
- **What we gave up:** deleting a tenant cascades to `chunks` and `documents` via `tenant_id` FKs, and with no index on the referencing column each cascade is a sequential scan of `chunks`. Acceptable while tenant deletion is rare/administrative. Per-document operations are not affected (`uq_chunks_document_id_chunk_index` leads with `document_id`).
- **Fallback:** if tenant delete or tenant-filtered reads become slow, re-add `ix_chunks_tenant_id` (and `documents`) and pin the test plan with `SET LOCAL enable_bitmapscan = off` (together with `enable_seqscan = off`) in `test_filtered_ann_with_hnsw` so the planner still has to choose HNSW.

### Re-posting content that is still PENDING (commit 4d)
- **Behaviour:** `POST /documents` for content whose document is still `PENDING` (another request is ingesting it) runs `ingest_document` again. The `SELECT ... FOR UPDATE` + re-check in the write transaction keeps the data correct (one set of chunks), but the embedding work is done twice.
- **Accepted until Day 9:** the background worker will dedupe ingestion jobs by document id, after which the route only enqueues.
- **Related:** re-posting identical content with a different title returns the existing document unchanged (200, original title); pinned by `tests/test_documents_repost.py`.

### `application_name` on the runtime engine (commit 4d)
- The runtime engine sets `application_name = helphub-<pid>` (`app/db/session.py`), and the transaction spy tests filter `pg_stat_activity` on it, so other clients of the shared dev database cannot affect them.
- **Day 9 note:** the name is fixed when `app.db.session` is imported. A worker process forked after that import keeps the parent's pid in its connections' `application_name` unless it builds its own engine after the fork.
