# HelpHub: cleanup to production plan (backend only)

Branch: `cleanup/measure` (rename to `cleanup/lean` at Session A start).
Inputs: `docs/cleanup/evidence.md` (2026-10-17), owner decisions below.
Rule for every claim in this plan and in Claude Code's work: **verified** means a command or source confirmed it. Anything else is marked **VERIFY** and has a spike in Session A. Never state a guess as a fact.

## 1. Decisions already made

| # | Decision |
|---|---|
| D1 | Keep 16 routes (list in section 3). Cut `/search/keyword`, `/search/hybrid`, `/documents/{id}/chunks`, `/health/db`. `/users` stays: admins add users to their tenant. |
| D2 | Drop Elasticsearch entirely. One search = pgvector + tsvector fused in a single Postgres query (RRF computed in SQL). A `mode` parameter is added only if the compare-retrieval page is confirmed later. |
| D3 | Keep a slim eval script that re-measures retrieval on the new stack. Move the tenant-cleanup queries out of `app/`. |
| D4 | Keep fastembed in-process. Measure full-app memory under load before committing to Render's free instance. |
| D5 | Free-tier trade-offs accepted. Keep-alive via an uptime bot (see section 6). |
| D6 | The "no edits to existing tests" and "never commit a red test" rules are relaxed on the refactor branch only. Every deleted or edited test is listed in its commit message. |
| D7 | Backend cleanup: 3 planned sessions (A, B, C). Reserve D and E for stabilisation; take as many as needed. Quality over speed. |
| D8 | Test pruning and per-file measurement happen after the refactor, not before. |
| D9 | **No new feature and no frontend work until Gate 0 (section 2) passes.** |

## 2. Gate 0: "lean and stable" (the only door to features and UI)

All must hold, each checked by a command and recorded in `docs/cleanup/gate0.md`:

1. `grep -ri elasticsearch backend/ docker-compose.yaml pyproject.toml` returns nothing outside git history.
2. `scripts/gate.sh --full` green, run without pipes, exit code checked.
3. `ruff check --preview --select PLR0913,PLR0915,C901` reports 0 hits in `app/`.
4. import-linter has a new contract: `app.services` may not import `sqlalchemy` or `asyncpg`. 0 ignored imports except those listed in `accepted-risks.md`.
5. Exactly one implementation of the traceback-frame logger and one of SQLSTATE extraction, both in `app/core/`.
6. `app/` contains no eval-only code (no cleanup queries, no `eval-` slug special case unless Session A decides it must stay and records why).
7. App container runs on the target host class with measured peak RSS under the load script, recorded with the number.
8. Retrieval eval re-run on the new stack; AR-10 and AR-18 updated with the new numbers (or closed).
9. Live smoke script passes against Render + Supabase (Session C), and a 48-hour soak shows no failed health checks other than the first wake.

## 3. Target route set (16)

`POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `GET /users`, `POST /users`, `GET /users/{id}`, `POST /documents`, `POST /documents/upload`, `GET /documents`, `GET /documents/{id}`, `DELETE /documents/{id}`, `POST /search`, `POST /chat/stream`, `GET /conversations`, `GET /conversations/{id}/messages`, `GET /health`. That is 16 of the current 20 routes. Session C adds `GET /health/ready` (replacing `/health/db`), `POST /auth/refresh` and `POST /auth/logout`, for 19 in total.

**Registration default:** `allow_public_registration` defaults to `False` from Session C onward and is switched to `True` as the very last step of the whole project, after Gate 0, the soak and the frontend. Until then, tenants are created by a seed script run by the owner. **VERIFY** in Session A that no test depends on the current default of `True` (tests that need registration must set it explicitly).

## 4. Session A: baseline, spikes, and the cut

Goal: everything that weighs the project down is gone, tests green.

**A0. Hygiene (before any code change)**
- Commit the CLAUDE.md fix on its own: remove the pasted instruction text and stray note at its tail. Check `.gitignore` covers `backend/dist/`, `.cache/`, `docs/cleanup/` working files as intended.
- Create `docs/review/backlog.md` with IDs (the "Review backlog" move CLAUDE.md asks for).
- Tag the current commit `pre-lean`.

**A1. VERIFY spikes (record the result of each in `docs/cleanup/spikes.md`)**
1. Does `db/tenant_context.set_tenant` use a transaction-local setting? Test RLS isolation through Supabase's pooler. Transaction mode does not support prepared statements (verified by Supabase docs); asyncpg needs `statement_cache_size=0` there. Direct connections need IPv6; session mode is the fallback (verified).
2. Can Render reach Supabase directly (IPv6), or must it use the session pooler?
3. Can you create `helphub_owner` and `helphub_app` on Supabase and have app queries run as `helphub_app` with RLS enforced? Run the existing isolation tests against it.
4. Are the tables reachable through Supabase's auto-generated REST API with the public keys? If yes, move them out of the exposed schema or disable the Data API. RLS keyed to a session setting does not protect against that path by itself.
5. Render free instance RAM: sources disagree (512 MB vs 256 MB). Read Render's own pricing page and record the figure.
6. Measure peak RSS of the full app under a short load (upload + 20 chat requests), not just the model load (256 MB, measured).

**A2. The cut (small commits, tests kept green at each step)**
1. Delete the 4 cut routes and their service functions and tests (`/search/keyword`, `/search/hybrid`, `/documents/{id}/chunks`, `/health/db`). Keep the `/users` routes and `require_admin`.
2. Remove Elasticsearch: `es_client`, `es_index`, `keyword_search`, `search_sync`, `reindex`, `hybrid_search`, `rrf` (re-created in SQL in Session B), `scripts/reindex.py`, the ES calls inside `documents.py` ingest and delete, the dependency, the compose service, the `es_*` settings, and `tests/search/*es*`, `test_reindex*`, `test_hybrid*`.
3. Dead-code pass. Each vulture candidate in evidence section C1 is checked by grep and by deleting and running the tests before removal: `get_embedding`, `get_embeddings_batch`, `search_chunks`, `es_ready`, `explain_statement`, `ERROR_CODES`, `vector_fallback`, `chat_events`, `search_index_error`. The `search_index_status` column and its CHECK constraint (migration 0007) die with ES: add a new migration dropping them; do not edit 0007.
4. Move eval-only repository queries (`list_candidates`, `delete_if_candidate`, `existing_ids`, `id_for_slug`, `count_slug_prefix`) into `eval/`; `list_ids` serves the reindex path, so **VERIFY** it is unused after ES goes, then delete it, using a connection supplied by the eval runner. Decide whether the `eval-` reserved-slug check stays; record why.
5. Retire or reword accepted risks: AR-04 and AR-06 go with ES; AR-11 and the alias-refresh half of AR-13 need rewording; keep the rest.

**Exit check A:** gate `--full` green; `grep elasticsearch` empty; route table equals section 3; spikes file complete; commit message lists every deleted test file.

## 5. Session B: Postgres search, then SOLID and DRY

**B1. Search in Postgres**
- Migration: generated `tsvector` column on `chunks` (config chosen in the spike, default `english`) with a GIN index, alongside the existing HNSW index. Check the 500 MB free database limit against projected index size with the demo corpus.
- One repository function builds the fused query: vector candidates and tsvector candidates, each filtered by `tenant_id`, ranked, combined with RRF in SQL. One tenant filter, defined once.
- `POST /search` calls one service function. Chat uses the same function (no second retrieval path).
- Re-prove isolation: the existing search-isolation tests are ported, not deleted. Add a test that a tsvector query cannot return another tenant's chunk.
- The code-literal rule from eval gate R2 is revisited here, since it was built around BM25. Do not port it blindly; Session D re-derives the gate from measurements.

**B2. SOLID and DRY (pragmatic; protocols only at real seams)**
- Single responsibility: split every function over 25 statements. In order: `api/uploads.py:parse_multipart` (40, route layer; move the logic out of `api/`), `documents.py` ingest, `reindex_all` goes with ES, then the `eval/` ones in Session D.
- Dependency inversion: services stop importing `sqlalchemy`; SQL lives in repositories (`auth`, `documents`, `search`, `users` services import it today per the module table). Keep the `EmbeddingProvider` and `LLMProvider` protocols. Do not add new protocols without a second implementation or a test double that needs one.
- DRY: one traceback-frame helper and one SQLSTATE helper in `app/core/` (currently three and two copies); `chat.py` stops importing a utility from `documents.py`. Replace the 8 PLR0913 signatures with small parameter objects only where it reads better.
- Open/closed: replace the six-branch `isinstance` chain in `llm.py` with a mapping from exception type to `(error, retryable)`; this also confines `groq` to the provider.
- Interface segregation: `chat_messages.add` (9 args) is the first PLR0913 fix.

**Exit check B:** Gate 0 items 3, 4, 5 pass; isolation suite green on pgvector + tsvector; `/search` p95 recorded on the demo corpus.

## 6. Session C: container, hardening, CI, deploy

1. **Dockerfile** (none today): multi-stage, non-root, fastembed model cache baked in, one process. Apply the memory limit found in spike 6. PDF workers: re-check the per-worker memory cap and concurrency against the host RAM, since each worker caps at 512 MB of address space and two can run.
2. **Config for production:** make `app_env` actually branch (nothing does today). Set the default of `allow_public_registration` to `False` (see section 3; it is flipped to `True` only at the very end of the project, and the abuse risk is recorded in `accepted-risks.md` at that point). Add CORS for the frontend origin. Keep secrets as `SecretStr`.
3. **Rate limiting** on login, search and chat (closes AR-07 and the rate-limit half of AR-13). Refresh tokens (closes AR-08): implemented, with rotation and reuse detection (owner decision; not documented as an accepted risk).
4. **`GET /health/ready`:** runs `SELECT 1` through the app role; replaces `/health/db` and removes AR-12 (no untenanted session in `api/`).
5. **CI** (`.github/workflows`): `gate.sh --full` against a `pgvector/pgvector:pg16` service container; dependency audit; build the image.
6. **Deploy:** Render web service + Supabase. Run migrations with the owner URL as a separate step, never from the app's runtime role. **VERIFY** whether Render's free tier supports a pre-deploy command; if not, run migrations from CI.
7. **Keep-alive (uptime bot):** ping `/health/ready` at an interval under 15 minutes. Facts: Render's free service spins down after 15 minutes without inbound traffic and needs about a minute to wake; Supabase free pauses after a week without database activity, and a ping that touches the database is what prevents it. **VERIFY** the bot's free-tier interval, and that `SELECT 1` counts as database activity (test: leave the project idle past the limit, or read Supabase's docs). One always-on free service uses about 744 of the workspace's 750 free hours, so it must be the only free web service in that workspace.
8. **Backups:** Supabase free has none. Add a scheduled `pg_dump` from CI to storage you control, or record the gap in the README.
9. **Live smoke script:** register, upload a document, search, chat, delete, against the deployed URL.

**Exit check C:** Gate 0 items 7 and 9 start; CI green on a clean clone.

## 7. Sessions D and E (reserved, use as many as needed)

**D. Relevance and tests**
- Re-run the slim eval on the new stack; re-derive the retrieval gate; update AR-10 and AR-18 with numbers (earlier numbers came from ES + dev split, so they cannot be reused).
- Run the per-file test runtime and unique-coverage measurement (command in evidence section E). Produce the table; the owner approves deletions; merge the 40 files with 1 to 4 tests where it helps.
- Split the `eval/` functions over 25 statements.

**E. Soak and bug-hunt**
- 48-hour live soak with the uptime bot. Check: cold-start behaviour, Supabase pause avoided, memory stays under the host limit, no RLS leak under concurrent tenants, citation and refusal behaviour on questions with no answer.
- Fix every defect found; Gate 0 is recorded only after a clean soak.

## 8. After Gate 0

Only then: refusal/escalation gate, Next.js UI, streaming chat with citations, compare-retrieval page with the seeded demo tenant (this is when a `mode` parameter is decided), README and video. Each feature gets the same rules: a test, a gate pass, and a note in `backlog.md`.

## 9. Working rules for Claude Code during this plan

- One concern per commit; tests green at each commit.
- Do not read `.env`. Do not run two pytest sessions at once.
- Report only measured numbers; label anything not measured.
- If a spike contradicts a decision above, stop and report; do not work around it.

## Sources (hosting facts, checked 2026-10-17)

- Supabase pricing and free-tier limits: https://supabase.com/pricing
- Supabase pooler and prepared statements: https://supabase.com/docs/guides/troubleshooting/disabling-prepared-statements-qL8lEL
- Render free-tier behaviour, as reported: https://temps.sh/blog/render-pricing-2026 (verify against render.com/docs/free)