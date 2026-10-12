# Day 5 plan: Elasticsearch keyword search

Postgres stays the source of truth. ES is a derived index that returns ids and scores only; every hit is re-read from Postgres (explicit `tenant_id` + RLS) before it is returned. The tenant filter lives in one place: `build_query`.

## Decisions
- Index `chunks-v1` behind alias `chunks` (settings `es_alias`); tests use a per-session prefix `test-<uuid>` and delete it in `finally`.
- Mapping (`dynamic: strict`, 1 shard, 0 replicas): `tenant_id` keyword, `document_id` keyword, `chunk_index` integer, `title` text (english), `content` text (english) with subfield `content.codes` (analyzer `code_analyzer`). `_id` = chunk uuid.
- `code_analyzer`: whitespace tokenizer, lowercase, `word_delimiter_graph` (preserve_original, catenate_all), tuned by `_analyze` experiments.
- Bulk indexing: `elasticsearch.helpers.async_bulk`, `raise_on_error=False`, failure counting, ~500 per batch, explicit timeouts, no refresh in production code. `delete_by_query` uses `conflicts="proceed"`.
- `POST /search/keyword`: `CurrentPrincipal`; `KeywordSearchRequest` has `extra="forbid"` (a body `tenant_id` is a 422, no search runs); score is the raw BM25 score, not comparable to the vector score; ES down -> 503 generic body.
- The app starts and `/health` works with ES down; index creation is lazy.
- ES errors never reach responses or logs beyond class name / status code / ids.
- `scripts/reindex.py` reads with the runtime role through `tenant_transaction` (tenants listed from `tenants`); never the owner connection.
- ES tests use a short `es_timeout_seconds` and fail (never skip) when ES is unreachable.

## Query design measurements
(filled in commit 2)

## Checklist
- [x] Commit 0: hygiene (groq default 120b, kwargs test, amendment tests, CLAUDE.md)
- [ ] Commit 1: infrastructure (compose, client, settings, test prefix)
- [ ] Commit 2: mapping, analyzers, query, hydration
- [ ] Commit 3: sync (migration 0007, index_document, delete sync, reindex) and API
- [ ] Stretch: per-tenant filtered aliases
- [ ] Final verification V1-V12
