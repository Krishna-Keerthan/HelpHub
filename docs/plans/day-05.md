# Day 5 plan: Elasticsearch keyword search

Postgres stays the source of truth. ES is a derived index that returns ids and scores only; every hit is re-read from Postgres (explicit `tenant_id` + RLS) before it is returned. The tenant filter lives in one place: `build_query`.

## Decisions
- Index `chunks-v1` behind alias `chunks` (settings `es_alias`); tests use a per-session prefix `test-<uuid>` and delete it in `finally`.
- Mapping (`dynamic: strict`, 1 shard, 0 replicas): `tenant_id` keyword, `document_id` keyword, `chunk_index` integer, `title` and `content` text (english), each with a subfield `.codes` (analyzer `code_analyzer`). `_id` = chunk uuid.
- `code_analyzer`: whitespace tokenizer, lowercase, `word_delimiter_graph` (preserve_original, catenate_all), tuned by `_analyze` experiments.
- Bulk indexing: `elasticsearch.helpers.async_bulk`, `raise_on_error=False`, failure counting, ~500 per batch, explicit timeouts, no refresh in production code. `delete_by_query` uses `conflicts="proceed"`.
- `POST /search/keyword`: `CurrentPrincipal`; `KeywordSearchRequest` has `extra="forbid"` (a body `tenant_id` is a 422, no search runs); score is the raw BM25 score, not comparable to the vector score; ES down -> 503 generic body.
- The app starts and `/health` works with ES down; index creation is lazy.
- ES errors never reach responses or logs beyond class name / status code / ids.
- `scripts/reindex.py` reads with the runtime role through `tenant_transaction` (tenants listed from `tenants`); never the owner connection.
- ES tests use a short `es_timeout_seconds` and fail (never skip) when ES is unreachable.

## Query design measurements
Corpus (one tenant): `E-4012` (card declined), `E-4013` (card expired), `AB-1234-XL`, `AB-9999-XL`, a billing doc ("update your payment card"). Top hits with scores.

First attempt, a single `multi_match` over `content`, `content.codes^2`, `title` (default OR):

| Query | Result |
|---|---|
| `E-4012` | E-4012 doc 2.5, **E-4013 doc 1.0** (shares the fragment `e`) |
| `AB-1234-XL` | AB-1234-XL 3.19, **AB-9999-XL 2.24** (shares `ab`, `xl`) |
| `why was my card declined with E-4012` | E-4012 5.31, E-4013 2.0, billing 1.54 |
| `how do I update my card` | billing 7.27, E-4013 4.21, E-4012 2.0 |

`minimum_should_match: 75%` fixed the sentence-with-code case but returned nothing for the plain question. Fragments were the cause, so the final design splits the query in `build_query`: identifier-like tokens (a digit, an underscore, or an inner hyphen) go to `content.codes^3`/`title.codes^4` and are matched **exactly** (search analyzer `code_search` = whitespace + lowercase, so `e-4012` must equal an indexed token); the remaining words go to `content`/`title^1.5` with `minimum_should_match`:

| words `minimum_should_match` | `E-4012` | `why was my card declined with E-4012` | `how do I update my card` | `AB-1234-XL` |
|---|---|---|---|---|
| **50% (chosen)** | E-4012 6.55 | E-4012 8.66 (E-4013 absent) | billing 2.92 | AB-1234-XL 5.95 (AB-9999-XL absent) |
| 75% / `2<75%` / `2<-25%` | same | E-4012 6.55 | **empty** | same |

`_analyze` on `content.codes` (analyzer `code_analyzer`, `word_delimiter_graph` with `preserve_original` + `catenate_all`):

| Text | Tokens |
|---|---|
| `E-4012` | `e-4012`, `e4012`, `e`, `4012` |
| `AB-1234-XL` | `ab-1234-xl`, `ab1234xl`, `ab`, `1234`, `xl` |
| `ERR_CONN_RESET` | `err_conn_reset`, `errconnreset`, `err`, `conn`, `reset` |
| `v2.3.1` | `v2.3.1`, `v231`, `v`, `2`, `3`, `1` |

Variants tried: `preserve_original` only (no `e4012`, so `E4012` would not match); `split_on_numerics=false` (turns `v2.3.1` into `v2`, `3`, `1`, worse). A `pattern_replace` char filter turns sentence punctuation next to a code (`E-4012:`) into a space, otherwise the token `e-4012` is never produced.

## Checklist
- [x] Commit 0: hygiene (groq default 120b, kwargs test, amendment tests, CLAUDE.md)
- [x] Commit 1: infrastructure (compose, client, settings, test prefix)
- [x] Commit 2: mapping, analyzers, query, hydration
- [ ] Commit 3: sync (migration 0007, index_document, delete sync, reindex) and API
- [ ] Stretch: per-tenant filtered aliases
- [ ] Final verification V1-V12
