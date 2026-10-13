# Day 6 plan: hybrid search, RRF, evaluation set

Stub written during the Day 6 preflight; fill in measurements as the day goes.

## Goal
Hybrid search that combines BM25 (Elasticsearch) and vector (pgvector) rankings with reciprocal rank fusion, and a small author-written evaluation set to measure it.

## Scope and decisions
- New `POST /search/hybrid` returning `{results, degraded}`. `degraded` is true when one branch failed or timed out and the results come from the other branch only.
- Reciprocal rank fusion with `rrf_k = 60`; each branch contributes `candidates = 50` ids before fusion.
- Each branch runs in its own session/transaction (`CurrentPrincipal` plus short `tenant_transaction`s, never `TenantSession`); no DB transaction is held across the ES call or the embedding call.
- ES still returns ids and scores only; every hit is re-read from Postgres with `tenant_id` + RLS. Scores from the two branches are never merged directly (AR-11); only ranks enter RRF.
- Evaluation is retrieval-only: no LLM calls.
- Evaluation set: 40 author-written questions, split 24 dev / 16 test. The test split is not looked at while tuning (retrieval threshold AR-10 is tuned on dev only).

## Carried over from the preflight
- The original `test_search_dead_tuples.py` 13/20 failure is still unexplained (not reproduced in 60+ clean runs).
- `test_search_hermetic.py::test_hnsw_path_finds_small_tenant_without_fallback` and `test_search_isolation.py::test_filtered_ann_with_hnsw` fail in roughly 1 of 8 isolation sessions on a table proven clean (`n_dead_tup = 0`): the ANN stage returns fewer than 3 hits on a freshly seeded graph. Decide how hybrid search treats a short ANN branch (the exact fallback already exists).

## Checklist
- [ ] Hybrid service: two independent branches, RRF fusion, `degraded` flag
- [ ] `POST /search/hybrid` route (`CurrentPrincipal`, `extra="forbid"` body) and tests (tenant scoping, one branch down, both down)
- [ ] Evaluation set: 40 questions, 24 dev / 16 test, stored in the repo
- [ ] Evaluation runner (retrieval-only) and a recorded baseline per branch and for hybrid
- [ ] Re-tune the provisional retrieval threshold on dev only (AR-10); revisit AR-11
- [ ] Day-end: `scripts/gate.sh --full` green, then `/day-review`
