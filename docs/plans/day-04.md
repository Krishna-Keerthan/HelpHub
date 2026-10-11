# Day 4 plan

## Provisional min_retrieval_score (seed for Day 6 evaluation)

**Provisional `min_retrieval_score = 0.59`** (midpoint of the gap below).

Measured with `backend/scripts/calibrate_threshold.py` (run from `backend/`:
`uv run python scripts/calibrate_threshold.py`). Model: `BAAI/bge-small-en-v1.5`,
score = cosine similarity of the top hit (same as `/search`'s `1 - cosine distance`).
Corpus: 8 inline demo support passages (password reset, invites, billing, cancel,
2FA, CSV export, API rate limit, uploads); in-memory, no DB.

| Group (10 queries each) | min | mean | max |
|---|---|---|---|
| Relevant (paraphrased) | 0.6836 | 0.7813 | 0.8846 |
| Irrelevant | 0.3965 | 0.4657 | 0.4952 |

Gap: (0.4952, 0.6836). Lowest relevant: "How do I turn on 2FA for my account?" (0.6836).
Highest irrelevant: "What's the best way to train for a marathon?" (0.4952).

Caveats: tiny corpus and hand-written queries, so this is a seed, not a verdict.
Real tenant corpora are larger and noisier, and near-miss off-topic questions
(e.g. other-product support questions) will score higher than these. Day 6 should
re-measure with harder negatives and tune.

### Per-query top-hit scores

Relevant: 0.7820, 0.7302, 0.7778, 0.7836, 0.6836, 0.8450, 0.7770, 0.7873, 0.8846, 0.7621
Irrelevant: 0.3965, 0.4844, 0.4636, 0.4947, 0.4833, 0.4952, 0.4878, 0.4832, 0.4089, 0.4598

## Day 4 checklist
- [x] Commit 0: hygiene (PDF queue wait 503 + Retry-After; worker import isolation; chunks-list tenant bind; no planner flags in app/)
- [x] Commit 1: schema (0006) + providers (one existing assertion changed: SecretStr count 3 -> 4, approved)
- [x] Commit 2: prompt + orchestration
- [ ] Commit 3: API (POST /chat/stream, conversations)
