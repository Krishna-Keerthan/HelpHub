# Retrieval evaluation

Generated 2026-10-14. Retrieval only; no LLM is called.

## Environment

- git_sha: 2dab2fa80ac0
- dirty (tracked modifications only): no
- untracked files: none
- elasticsearch server: 9.5.5
- elasticsearch client: (9, 5, 1)
- pgvector: 0.8.7
- hnsw_index: hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='64')
- hnsw_ef_search: max(40, k), capped at 1000
- hnsw_iterative_scan: relaxed_order
- embedding model: BAAI/bge-small-en-v1.5
- documents: 24
- chunks: 49
- chunker: max_chars=1000, overlap=150
- rrf_k: 60
- hybrid_candidates: 50
- min_retrieval_score (unchanged): 0.59
- python: 3.12.3
- cpu_count: 2
- machine: Linux 6.6.114.1-microsoft-standard-WSL2 x86_64
- questions.yaml sha256: 5a871c1f79e0440e8f0cf5281801a0f6cee8d97a82dac5c18fb3c11114c2deeb
- corpus files sha256 (first 16): INDEX.md=508b7462fc80c4fb, account-recovery.md=256a730b4a303e34, api-authentication.md=22d1a95d23dc55d3, api-error-reference.md=44b5d78d1f610121, api-rate-limits.md=3ec23d63b72e3e5c, audit-logs.md=cae927ef415e2ad7, billing-faq.md=ed50969ac3f61d28, changelog-v2-3.md=1281d85b7e24e084, changelog-v2-4.md=1a5b85b2c0167a25, data-export.md=567b2f51121ac8f2, desktop-client-install.md=19b584504e77e23b, getting-started.md=942011884fae558c, mobile-app-offline-mode.md=24d6a7609c38080b, notifications-and-realtime.md=e71dc69089246bf0, password-reset.md=5d39634d1f5b4dab, plans-and-pricing.md=20b66ff1610fcd91, refunds-and-cancellations.md=300a0a4beb059246, security-overview.md=1eca39558adbcdd5, sharing-and-permissions.md=c18c12e41ef8a3ae, sso-error-reference.md=7fedd9d2870e01f5, sso-saml-setup.md=03b7d100bf156c00, storage-quotas.md=74121865a791899c, sync-client-troubleshooting.md=ef11071af96d6d9b, two-factor-authentication.md=88248b0866f4042a, webhooks.md=2bd86900d574236c

## Corpus and questions

24 documents, 49 chunks, 40 questions (unanswerable: dev 4, test 4).

| category | dev | test |
| --- | --- | --- |
| code | 5 | 3 |
| keyword | 4 | 2 |
| mixed | 5 | 3 |
| near_miss | 2 | 2 |
| off_topic | 2 | 2 |
| paraphrase | 6 | 4 |
| total | 24 | 16 |

## Retrieval metrics (answerable questions)

recall@5 = mean over questions of (distinct relevant chunks in the top 5) / (relevant chunks). MRR@10 = mean reciprocal rank of the first relevant chunk in the top 10.

### dev

| mode | category | n | hit@1 | hit@3 | hit@5 | MRR@10 | recall@5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| vector | ALL | 20 | 11/20 = 55% | 16/20 = 80% | 20/20 = 100% | 0.698 | 1.000 |
| vector | code | 5 | 2/5 = 40% | 4/5 = 80% | 5/5 = 100% | 0.607 | 1.000 |
| vector | keyword | 4 | 3/4 = 75% | 4/4 = 100% | 4/4 = 100% | 0.875 | 1.000 |
| vector | mixed | 5 | 3/5 = 60% | 4/5 = 80% | 5/5 = 100% | 0.740 | 1.000 |
| vector | paraphrase | 6 | 3/6 = 50% | 4/6 = 67% | 6/6 = 100% | 0.622 | 1.000 |
| keyword | ALL | 20 | 8/20 = 40% | 15/20 = 75% | 15/20 = 75% | 0.567 | 0.750 |
| keyword | code | 5 | 2/5 = 40% | 5/5 = 100% | 5/5 = 100% | 0.667 | 1.000 |
| keyword | keyword | 4 | 2/4 = 50% | 4/4 = 100% | 4/4 = 100% | 0.750 | 1.000 |
| keyword | mixed | 5 | 3/5 = 60% | 5/5 = 100% | 5/5 = 100% | 0.800 | 1.000 |
| keyword | paraphrase | 6 | 1/6 = 17% | 1/6 = 17% | 1/6 = 17% | 0.167 | 0.167 |
| hybrid | ALL | 20 | 11/20 = 55% | 18/20 = 90% | 18/20 = 90% | 0.742 | 0.900 |
| hybrid | code | 5 | 3/5 = 60% | 5/5 = 100% | 5/5 = 100% | 0.800 | 1.000 |
| hybrid | keyword | 4 | 3/4 = 75% | 4/4 = 100% | 4/4 = 100% | 0.875 | 1.000 |
| hybrid | mixed | 5 | 3/5 = 60% | 5/5 = 100% | 5/5 = 100% | 0.800 | 1.000 |
| hybrid | paraphrase | 6 | 2/6 = 33% | 4/6 = 67% | 4/6 = 67% | 0.556 | 0.667 |

Overall hit@5, Wilson 95% interval:

| mode | hit@5 | 95% interval |
| --- | --- | --- |
| vector | 20/20 = 100% | 84% to 100% |
| keyword | 15/20 = 75% | 53% to 89% |
| hybrid | 18/20 = 90% | 70% to 97% |

### test

| mode | category | n | hit@1 | hit@3 | hit@5 | MRR@10 | recall@5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| vector | ALL | 12 | 7/12 = 58% | 11/12 = 92% | 11/12 = 92% | 0.762 | 0.917 |
| vector | code | 3 | 2/3 = 67% | 2/3 = 67% | 2/3 = 67% | 0.714 | 0.667 |
| vector | keyword | 2 | 0/2 = 0% | 2/2 = 100% | 2/2 = 100% | 0.500 | 1.000 |
| vector | mixed | 3 | 2/3 = 67% | 3/3 = 100% | 3/3 = 100% | 0.833 | 1.000 |
| vector | paraphrase | 4 | 3/4 = 75% | 4/4 = 100% | 4/4 = 100% | 0.875 | 1.000 |
| keyword | ALL | 12 | 4/12 = 33% | 9/12 = 75% | 9/12 = 75% | 0.514 | 0.750 |
| keyword | code | 3 | 2/3 = 67% | 3/3 = 100% | 3/3 = 100% | 0.778 | 1.000 |
| keyword | keyword | 2 | 1/2 = 50% | 2/2 = 100% | 2/2 = 100% | 0.750 | 1.000 |
| keyword | mixed | 3 | 1/3 = 33% | 2/3 = 67% | 2/3 = 67% | 0.444 | 0.667 |
| keyword | paraphrase | 4 | 0/4 = 0% | 2/4 = 50% | 2/4 = 50% | 0.250 | 0.500 |
| hybrid | ALL | 12 | 8/12 = 67% | 12/12 = 100% | 12/12 = 100% | 0.833 | 1.000 |
| hybrid | code | 3 | 2/3 = 67% | 3/3 = 100% | 3/3 = 100% | 0.833 | 1.000 |
| hybrid | keyword | 2 | 2/2 = 100% | 2/2 = 100% | 2/2 = 100% | 1.000 | 1.000 |
| hybrid | mixed | 3 | 1/3 = 33% | 3/3 = 100% | 3/3 = 100% | 0.667 | 1.000 |
| hybrid | paraphrase | 4 | 3/4 = 75% | 4/4 = 100% | 4/4 = 100% | 0.875 | 1.000 |

Overall hit@5, Wilson 95% interval:

| mode | hit@5 | 95% interval |
| --- | --- | --- |
| vector | 11/12 = 92% | 65% to 99% |
| keyword | 9/12 = 75% | 47% to 91% |
| hybrid | 12/12 = 100% | 76% to 100% |

Vector exact fallback fired for 0 of 40 questions.

## Latency (ms)

3 warm-up queries discarded. vector includes the query embedding; keyword has none; hybrid includes the embedding plus both branches in parallel. Real FastEmbed model.

| mode | n | p50 | p95 |
| --- | --- | --- | --- |
| vector | 40 | 23 | 28 |
| keyword | 40 | 9 | 12 |
| hybrid | 40 | 29 | 42 |

## Integrity checks

| check | result |
| --- | --- |
| hybrid == fuse_rrf(branches) | PASS |
| evidence resolves | PASS |
| answerable have relevant chunks | PASS |
| splits 24/16 and categories | PASS |
| ES chunk count == DB chunk count | PASS |
| no degraded branch | PASS |

## Failure list

### dev: hybrid hit@5 worse than the better single mode (2)

- **q-003** (paraphrase): What is the maximum file storage capacity available for a single team tier member?
  - vector: `090b018c` Each member of a paid plan contributes storage to a pool shared by the whole workspace. A Team works; `6dd0d8cc` Add-ons. SKU AB-1234-XL adds 50 TB and is the largest standard pack; smaller packs are listed on the; `d6671ab8` You own your data and can take a complete copy at any time. There are three ways to export.  Workspa
  - keyword: `090b018c` Each member of a paid plan contributes storage to a pool shared by the whole workspace. A Team works; `f92c8fe9` The audit log records who did what and when in your workspace. It is available on the Business and E
  - hybrid: `090b018c` Each member of a paid plan contributes storage to a pool shared by the whole workspace. A Team works; `f92c8fe9` The audit log records who did what and when in your workspace. It is available on the Business and E; `6dd0d8cc` Add-ons. SKU AB-1234-XL adds 50 TB and is the largest standard pack; smaller packs are listed on the
- **q-005** (paraphrase): How do I create a personal credential for my automated scripts?
  - vector: `3633f399` 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name.; `1d76ace9` 1. Open Settings, Security, Single sign-on and choose Set up SAML. 2. Copy the Acme Cloud values sho; `22a9c45c` Single sign-on lets members log in through your company identity provider instead of with a separate
  - keyword: `70fcd578` Q: When am I charged? A: Annual plans are charged on the day you subscribe and every twelve months a
  - hybrid: `70fcd578` Q: When am I charged? A: Annual plans are charged on the day you subscribe and every twelve months a; `3633f399` 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name.; `1d76ace9` 1. Open Settings, Security, Single sign-on and choose Set up SAML. 2. Copy the Acme Cloud values sho

### dev: answerable questions no mode retrieved in the top 5 (0)

- none

### test: hybrid hit@5 worse than the better single mode (0)


### test: answerable questions no mode retrieved in the top 5 (0)

- none

## Gate evaluation under docs/eval/protocol.md: INVALID MEASUREMENT (see protocol Amendment 2)

**Do not quote these numbers as findings.** The eval tenant was loaded without each document's `# Title` line, so the corpus differs from the production ingest path. The raw numbers are kept below for audit only. The gate remains at 0.59 and is a known weak point.

Embeddings: `@cf/baai/bge-small-en-v1.5` (production model), 49 chunks / 24 documents in the dedicated tenant `eval-cloudflare`. Hybrid top-5, a question is answered if one hit has cosine >= t. Rule fixed on DEV, TEST run once (`docs/eval/test_result.json`).

| split | answerable wrongly refused (A) | unanswerable wrongly answered (U) |
| --- | --- | --- |
| DEV, R0 t = 0.67 (chosen) | 3/20 = 15% | 3/13 = 23.1% |
| DEV, best R1 (t = 0.67, s = 0.05) | 3/20 = 15% | 3/13 = 23.1% (ties R0, not strictly better) |
| TEST, R0 t = 0.67 | 3/12 = 25% | 4/18 = 22.2% |

Chosen by the protocol: minimise max(A_dev, U_dev); R1 is never strictly better than R0, so R0. **TEST fails** the criterion (A <= 15% and U <= 15%, i.e. at most 1/12 and at most 2/18). Wrongly refused: q-017 (code), q-031 and q-032 (keyword). Wrongly answered: u-006, u-010, u-014, u-016 (all near_miss).

Caveats (apply only if the measurement is repeated on the correct corpus): small samples (20 and 12 answerable, 13 and 18 unanswerable); with n = 18 even zero errors only bounds the true wrong-answer rate near 17% (rule of three: 3/18). The text score gave no gain over cosine alone on DEV. The gate stays at 0.59; no production code changed. Both the DEV and TEST figures above are invalid (Amendment 2).

## Gate analysis (closes AR-10) [older: Elasticsearch-era numbers, local vectors, superseded by the section above]

R1: answer iff best vector cosine >= T. R2: R1 OR an identifier-like token of the query occurs (case-insensitively) in a top-5 hybrid hit. False refusal = answerable question refused; false answer = unanswerable question answered. Counts are over dev: 20 answerable / 4 unanswerable, test: 12 answerable / 4 unanswerable.

### dev

| rule | T | false refusals | false answers | by category (refusals/answers) |
| --- | --- | --- | --- | --- |
| R1 | 0.50 | 0/20 | 2/4 | near_miss:0/2 |
| R1 | 0.52 | 0/20 | 2/4 | near_miss:0/2 |
| R1 | 0.54 | 0/20 | 2/4 | near_miss:0/2 |
| R1 | 0.56 | 0/20 | 2/4 | near_miss:0/2 |
| R1 | 0.58 | 1/20 | 2/4 | code:1/0 near_miss:0/2 |
| R1 | 0.60 | 1/20 | 2/4 | code:1/0 near_miss:0/2 |
| R1 | 0.62 | 2/20 | 1/4 | code:1/0 near_miss:0/1 paraphrase:1/0 |
| R1 | 0.64 | 2/20 | 1/4 | code:1/0 near_miss:0/1 paraphrase:1/0 |
| R1 | 0.66 | 2/20 | 1/4 | code:1/0 near_miss:0/1 paraphrase:1/0 |
| R1 | 0.68 | 6/20 | 1/4 | code:2/0 mixed:2/0 near_miss:0/1 paraphrase:2/0 |
| R1 | 0.70 | 6/20 | 1/4 | code:2/0 mixed:2/0 near_miss:0/1 paraphrase:2/0 |
| R2 | 0.50 | 0/20 | 2/4 | near_miss:0/2 |
| R2 | 0.52 | 0/20 | 2/4 | near_miss:0/2 |
| R2 | 0.54 | 0/20 | 2/4 | near_miss:0/2 |
| R2 | 0.56 | 0/20 | 2/4 | near_miss:0/2 |
| R2 | 0.58 | 0/20 | 2/4 | near_miss:0/2 |
| R2 | 0.60 | 0/20 | 2/4 | near_miss:0/2 |
| R2 | 0.62 | 1/20 | 1/4 | near_miss:0/1 paraphrase:1/0 |
| R2 | 0.64 | 1/20 | 1/4 | near_miss:0/1 paraphrase:1/0 |
| R2 | 0.66 | 1/20 | 1/4 | near_miss:0/1 paraphrase:1/0 |
| R2 | 0.68 | 2/20 | 1/4 | near_miss:0/1 paraphrase:2/0 |
| R2 | 0.70 | 2/20 | 1/4 | near_miss:0/1 paraphrase:2/0 |

### test

| rule | T | false refusals | false answers | by category (refusals/answers) |
| --- | --- | --- | --- | --- |
| R1 | 0.50 | 0/12 | 3/4 | near_miss:0/2 off_topic:0/1 |
| R1 | 0.52 | 0/12 | 3/4 | near_miss:0/2 off_topic:0/1 |
| R1 | 0.54 | 0/12 | 3/4 | near_miss:0/2 off_topic:0/1 |
| R1 | 0.56 | 0/12 | 3/4 | near_miss:0/2 off_topic:0/1 |
| R1 | 0.58 | 1/12 | 2/4 | keyword:1/0 near_miss:0/2 |
| R1 | 0.60 | 1/12 | 2/4 | keyword:1/0 near_miss:0/2 |
| R1 | 0.62 | 2/12 | 1/4 | code:1/0 keyword:1/0 near_miss:0/1 |
| R1 | 0.64 | 2/12 | 1/4 | code:1/0 keyword:1/0 near_miss:0/1 |
| R1 | 0.66 | 2/12 | 1/4 | code:1/0 keyword:1/0 near_miss:0/1 |
| R1 | 0.68 | 4/12 | 1/4 | code:1/0 keyword:2/0 near_miss:0/1 paraphrase:1/0 |
| R1 | 0.70 | 4/12 | 1/4 | code:1/0 keyword:2/0 near_miss:0/1 paraphrase:1/0 |
| R2 | 0.50 | 0/12 | 3/4 | near_miss:0/2 off_topic:0/1 |
| R2 | 0.52 | 0/12 | 3/4 | near_miss:0/2 off_topic:0/1 |
| R2 | 0.54 | 0/12 | 3/4 | near_miss:0/2 off_topic:0/1 |
| R2 | 0.56 | 0/12 | 3/4 | near_miss:0/2 off_topic:0/1 |
| R2 | 0.58 | 1/12 | 2/4 | keyword:1/0 near_miss:0/2 |
| R2 | 0.60 | 1/12 | 2/4 | keyword:1/0 near_miss:0/2 |
| R2 | 0.62 | 1/12 | 1/4 | keyword:1/0 near_miss:0/1 |
| R2 | 0.64 | 1/12 | 1/4 | keyword:1/0 near_miss:0/1 |
| R2 | 0.66 | 1/12 | 1/4 | keyword:1/0 near_miss:0/1 |
| R2 | 0.68 | 3/12 | 1/4 | keyword:2/0 near_miss:0/1 paraphrase:1/0 |
| R2 | 0.70 | 3/12 | 1/4 | keyword:2/0 near_miss:0/1 paraphrase:1/0 |

### Recommendation (chosen on dev only)

Rule: minimise dev false refusals subject to at most 1 dev false answer; among tied thresholds take the middle of the longest contiguous plateau (upper middle when even); equal plateaus prefer R1, then larger T.

**R2, T = 0.64** (plateau 0.62 to 0.66, 3 steps).

| split | false refusals | false answers |
| --- | --- | --- |
| dev | 1/20 | 1/4 |
| test | 1/12 | 1/4 |

Test numbers are reported without re-tuning. min_retrieval_score is NOT changed; Day 7 implements the gate.

### Identifier-like tokens in near_miss / off_topic questions

None of them contains an identifier-like token.

## Ablations (hybrid hit@5, answerable)

candidates=20 is approximated by truncating the recorded 50-candidate branch lists to their first 20 and re-fusing. Choices use dev; test is only the do-not-get-worse check.

| rrf_k | candidates | dev hit@5 | test hit@5 (check only) |
| --- | --- | --- | --- |
| 10 | 20 | 18/20 | 12/12 |
| 10 | 50 | 18/20 | 12/12 |
| 30 | 20 | 18/20 | 12/12 |
| 30 | 50 | 18/20 | 12/12 |
| 60 | 20 | 18/20 | 12/12 |
| 60 | 50 | 18/20 | 12/12 |
| 100 | 20 | 18/20 | 12/12 |
| 100 | 50 | 18/20 | 12/12 |

**Decision:** Keep rrf_k=60, candidates=50 (no setting improves dev hit@5 by at least 2 questions with test not worse).

## Limitations

- n = 40 author-written questions (24 dev / 16 test), written by the same person who built the corpus. Percentages are indicative, not precise; see the Wilson intervals.
- The corpus is synthetic (24 documents, one fictional company). Real tickets are messier.
- Each split has only 4 unanswerable questions, so every false-answer count rests on very few cases; gate results are indicative.
- Vector (cosine) and BM25 scores are not comparable (AR-11); only ranks enter RRF and the gate thresholds only vector cosine.
- HNSW recall is probabilistic (AR-15); vector numbers can differ slightly between builds of the index. Keyword numbers should not.
- Relevance is defined by exact evidence substrings; a chunk that answers the question without containing a listed snippet counts as a miss.
- Identifier tokens are extracted case-sensitively, so a code typed in lowercase gives R2 nothing to match.
- Latency is measured on one developer machine with the real embedding model, one query at a time.
