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
- `test_search_hermetic.py::test_hnsw_path_finds_small_tenant_without_fallback` and `test_search_isolation.py::test_filtered_ann_with_hnsw` fail in roughly 1 of 8 isolation sessions on a table proven clean (`n_dead_tup = 0`): the ANN stage returns fewer than 3 hits on a freshly seeded graph. Decided: a short ANN branch is handled by `search_in_session`'s exact fallback (see "Short ANN branch" below).

## Checklist
- [x] Hybrid service: two independent branches, RRF fusion, `degraded` flag
- [x] `POST /search/hybrid` route (`CurrentPrincipal`, `extra="forbid"` body) and tests (tenant scoping, one branch down, both down)
- [x] Evaluation set: 40 questions, 24 dev / 16 test, stored in the repo
- [x] Evaluation runner (retrieval-only) and a recorded baseline per branch and for hybrid
- [x] Re-tune the provisional retrieval threshold on dev only: recommendation R2 at T = 0.64 recorded (AR-10 stays OPEN, implementation in Day 7); AR-11 revisited
- [x] Day-end: `scripts/gate.sh --full` green, then `/day-review`

## Gate history note
c8551d4..7ebec87 passed the gate only because of untracked files (the checks read tracked files, so a clean checkout would have failed); 0c502ff repaired it. The gate now fails when untracked, non-ignored files exist under app/, tests/, eval/, alembic/, scripts/, .claude/ or docs/.

## Hybrid timeouts
The query embedding has its own limit (`embedding_timeout_seconds`, default 10 s). The vector branch budget is now `embedding_timeout_seconds + hybrid_branch_timeout_seconds` (10 + 3); the keyword branch stays at 3 s. Worst-case hybrid latency is therefore about 13 s (a slow-but-alive embedder, then a slow search). A branch that exceeds its budget is dropped and reported in `degraded`.

## Short ANN branch
Handled by `search_in_session`'s exact fallback, not by hybrid-specific code; covered by deterministic tests (no dependence on HNSW randomness):
- `tests/search/test_search_fallback_deterministic.py::test_short_ann_stage_triggers_exact_fallback`
- `tests/search/test_hybrid_search.py::test_short_ann_branch_still_returns_the_tenants_chunks_via_fallback`
- `tests/search/test_hybrid_search.py::test_healthy_ann_does_not_report_fallback`
The probabilistic HNSW tests stay conditioned on a reachability probe (AR-15).

## Day-end review
- Range: d044dc8..a660945 (eval work after the cleanup commit), then this closing commit (`day 6 close`).
- Agents run on the range: tenant-reviewer, design-reviewer, test-quality-reviewer, security-auditor (all four). 14 findings in total; severity split is not recorded in the repo.
- Status: the MEDs (fail-open candidates, delete re-check, `--keep` journal) were closed in a660945. This commit closes the tenant-filter gap and the delete race (single FOR UPDATE transaction, lock timeout), privatizes the unconditional delete, deflakes the hybrid timing tests and tightens the weak assertions. The tenant-reviewer re-ran once over this commit. The LOW items still open are in the backlog below.

## Review backlog (unfixed LOW items)
- `eval/run_eval.py:92` uses the untenanted `AsyncSessionLocal` directly (extension version / index definition lookups); candidate: a read-only `app/db/introspection.py`.
- `count_ids` (review finding; wording as reported, not re-verified today).
- Sequential transactions per scan: `list_candidates` opens one transaction per slug match. Slow for many candidates, correct because the delete re-checks.
- Regex dialect mismatch: `list_candidates` filters with PostgreSQL `~` and then Python `re`; `delete_if_candidate` uses Python `re` only. Harmless for the `^eval-[0-9a-f]{12}$` pattern, not for arbitrary ones.
- Remaining LOW test items from the test-quality review that today's assertion pass did not cover (details in the review report, not recorded in the repo).
