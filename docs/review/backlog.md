# Review backlog

Single place for unfixed review items. IDs are stable; update Status in place, never renumber.
Sources: docs/plans/day-05.md, docs/plans/day-06.md (items copied as recorded there, not re-verified unless noted). Accepted risks live in accepted-risks.md (AR-nn).

| ID | Item | Source | Severity | Status |
|---|---|---|---|---|
| BL-01 | `eval/run_eval.py:92` uses untenanted `AsyncSessionLocal` for extension/index lookups; candidate: read-only `app/db/introspection.py` | day-06 | LOW | Open |
| BL-02 | `count_ids` review finding (wording as reported, not re-verified) | day-06 | LOW | Open |
| BL-03 | `list_candidates` opens one transaction per slug match (slow for many candidates; delete re-checks) | day-06 | LOW | Obsolete: code deleted in B0 (recoverable from tag pre-lean) |
| BL-04 | Regex dialect mismatch: `list_candidates` uses PG `~` then Python `re`; `delete_if_candidate` Python `re` only | day-06 | LOW | Obsolete: code deleted in B0 (recoverable from tag pre-lean) |
| BL-05 | Remaining LOW test-quality items not covered by the assertion pass (details not recorded in repo) | day-06 | LOW | Open |
| BL-06 | `ensure_index` per call | day-05 | LOW | Obsolete when ES is removed (A2.2) |
| BL-07 | FAILED status on throwaway-index reindex | day-05 | LOW | Obsolete when ES is removed (A2.2) |
| BL-08 | NOT VALID constraint at scale (was AR-14) | day-05 | LOW | Obsolete: AR-14 closed, constraint dropped by migration 0008 |
| BL-09 | Weaker test assertions listed in the day-05 review | day-05 | LOW | Open |
| BL-10 | Stretch: per-tenant filtered aliases | day-05 | n/a | Skipped; obsolete with ES |
| BL-11 | Known flake: `tests/isolation/test_search_dead_tuples.py` failed 13/20 standalone once, 0/60 later; cause not found | day-06 | LOW | Open |
| BL-12 | `register` hashes the password before the slug check, so a 409 (taken slug) costs a full hash | C9 | LOW | Open |
| BL-13 | Argon2 hashing runs synchronously on the event loop (blocks other requests while hashing). **Measured 2026-10-20** (image `helphub-backend:c9b`, local Docker, 512 MB / 0.1 CPU, existing user, n as stated): one login alone, median of 10 = 4.40 s (range 3.90 to 4.78). Five simultaneous logins, 3 repetitions, latencies in s: [6.69, 24.19, 24.28, 24.38, 24.38], [21.99, 21.99, 21.89, 21.99, 21.89], [22.29, 22.29, 22.29, 22.29, 22.28]. A request in flight while a login hashes (5 trials, request sent 0.3 s after the login): `GET /health` 3.09 to 4.36 s (alone 0.00 to 0.01 s), `GET /documents` 3.19 to 4.57 s (alone 0.08 to 0.11 s), login itself 3.5 to 4.87 s. So other requests stall for about the length of the hash. Not measured: `/search` and `/chat` during a login (no Cloudflare credentials in this session; `GET /documents` used as the authenticated DB-bound request), a deployed Render instance, CPU contention from other containers. | C9 | MEDIUM | Open |

Note: login latency at 0.1 CPU is unmeasured (relevant to BL-12 and BL-13).
