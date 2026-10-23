# Retrieval gate: evaluation protocol (fixed before any scoring)

Written before any score has been computed for the kept unanswerable questions. Changing a rule below after scoring starts is a protocol violation and must be recorded as such.

## 1. Questions and splits

- **Unanswerable:** the questions marked `stays` in `backend/eval/unanswerable_decisions.json` (kept only; `y` and `u` answers are removed). Their `split` is the one copied from `unanswerable_candidates.json`, never recomputed. Counts: DEV 13 (near_miss 5, off_topic 8), TEST 18 (near_miss 10, off_topic 8); 31 in all.
- **Answerable:** the answerable questions in `backend/eval/questions.yaml` keep their existing split: DEV 20, TEST 12; 32 in all.

## 2. What the gate does today (and what is measured)

`app/services/chat.py` searches in hybrid mode with `chat_top_k` (5) and keeps a retrieved chunk only if that chunk's own `score` (its cosine similarity to the question, whichever branch found it) is at least `min_retrieval_score` (0.59). The question is answered if at least one chunk is kept, otherwise refused. The rules below use the same per-chunk reading: **a question is answered if at least one of the top-5 hybrid hits satisfies the rule's condition on that same hit; otherwise it is refused.** "Best cosine" in R0 is the maximum `score` over those hits, which is the same thing.

`text_score` is the internal `SearchHit.text_score` (commit db97039): `ts_rank_cd(search_tsv, tsquery, 32)` for the keyword branch of the fused query, i.e. the raw cover-density rank divided by (rank + 1), in [0, 1). It is `null` when the chunk was not among the keyword candidates; **null counts as 0**. It is not used for ordering and is not in the API.

## 3. Error rates

- **A** = share of answerable TEST questions that the gate wrongly refuses.
- **U** = share of kept unanswerable TEST questions that the gate wrongly answers.
- On DEV the same two rates are written A_dev and U_dev.

## 4. Rules

- **R0:** answer only if best cosine >= t (refuse when best cosine < t).
- **R1:** answer only if best cosine >= t **and** text_score >= s, both on the same hit (refuse otherwise). With s = 0.00, R1 is identical to R0.

## 5. Tuning (DEV only, fixed grid)

- t grid: 0.50 to 0.80 in steps of 0.01 (31 values).
- s grid: 0.00 to 0.50 in steps of 0.05 (11 values).
- Selection: minimise max(A_dev, U_dev). Ties go to the higher threshold t.
- R1 is chosen only if it is **strictly better** than the best R0 on that measure; otherwise R0 is chosen.
- Tie-break among R1 candidates with equal max and equal t: the higher s. (Added to make the selection deterministic; confirmed by the owner, see Amendment 1.)
- TEST is not looked at while tuning.

## 6. TEST (once)

- TEST is evaluated exactly once with the chosen rule. The result is recorded as it comes out, with no re-tuning afterwards.
- The TEST runner refuses a second run through a lock file: `docs/eval/test_result.json` (see Amendment 1).

## 7. Pass criterion

The chosen rule passes if A_test <= 15% and U_test <= 15%. With the TEST sizes that means at most 1 of 12 wrongly refused answerable questions (2 of 12 is 16.7%) and at most 2 of 18 wrongly answered unanswerable questions (3 of 18 is 16.7%).

If neither rule passes, the gate stays as it is today and AR-10 and AR-18 record the result honestly.

## 8. Reporting

Report counts with their denominators (for example 1/12 and 2/18), for DEV and TEST, for the chosen rule and for R0 and R1 separately. Note that with n = 18 unanswerable TEST questions even zero errors only bounds the true wrong-answer rate near 17% (rule of three: 3/18).

## 9. Amendments (recorded before any scoring)

**Amendment 1.** Written before any DEV or TEST score exists.

1. The tie-break "higher s" (among R1 candidates with equal max and equal t) is confirmed.
2. The 8 older unanswerable questions in `backend/eval/questions.yaml` (`answerable: false`) are excluded. The unanswerable set is exactly the 31 kept questions of section 1.
3. The TEST runner refuses to run if `docs/eval/test_result.json` exists. That file is the lock. A re-run needs the file deleted and a written amendment here first.
4. The measurement uses the production embedding model: `EMBEDDING_PROVIDER=cloudflare` (`@cf/baai/bge-small-en-v1.5`, cls pooling), in a dedicated eval tenant. Vectors from any other provider are not used.
