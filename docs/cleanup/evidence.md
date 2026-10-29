# Cleanup evidence (read-only audit, 2026-10-17)

Branch `cleanup/measure`. No code changed, no tests deleted, `.env` not read.
Tools: ruff `--preview --isolated` (PLR), `uvx vulture/pylint/pip-audit/deptry` (ephemeral envs, not added to the project).

**Not measurable here:** `docker` is absent in this WSL distro; Postgres (5432) and ES (9200) refuse connections. So no test runtimes, no coverage, no unique-coverage numbers (see E). Start services, then rerun the commands in E.

## A. Duplicate code and repeated patterns

pylint R0801 (min 6 lines) found only trivial overlaps:
- `app/schemas/search.py:67-75` / `:36-43` vs `app/services/hybrid_search.py:39-47`: response/hit field blocks mirror each other (schema vs dataclass).
- `eval/cleanup.py:146-156` vs `eval/run_eval.py:394-404`: the `if __name__ == "__main__"` CLI tail.

Repeated patterns found by grep (not clones, but 2-3 copies of one idea):
- **Traceback-frame logging helper, 3 copies:** `app/services/documents.py:96` (`_frames`), `app/services/hybrid_search.py:88` (`_frames`), inline in `app/services/chat.py:284`. Same rule (CLAUDE.md: file:line only, no messages). Candidate: one helper in `app/core/`.
- **SQLSTATE extraction:** `sqlstate_of` lives in `services/documents.py` and `services/chat.py:28` imports it from there (service-to-service import for a utility).
- **ES alias/index name:** `alias_name()` called at 8 sites across `es_client`, `es_index`, `keyword_search`, `search_sync`; consistent, not duplicated.
- **Tenant transaction boilerplate:** `get_tenant_session` / `tenant_transaction` appear at 25 sites in `app/`; expected by the layering rule.
- **app/ vs eval/:** no shared code; `eval/` imports from `app` only (`grep "from eval" app scripts` returns nothing).

## B. Design smells

### B1. Concrete-library imports vs Protocols
| Service | Concrete import | Protocol? |
|---|---|---|
| `services/llm.py:16-17` | `groq`, `AsyncGroq` | Yes: `LLMProvider` (`:77`) |
| `services/embeddings.py:17,77` | `numpy`, lazy `fastembed` | Yes: `EmbeddingProvider` (`:54`) |
| `services/es_client.py:10` | `elasticsearch.AsyncElasticsearch` | No |
| `services/es_index.py:10` | `AsyncElasticsearch`, `BadRequestError` | No |
| `services/keyword_search.py:14` | `AsyncElasticsearch`, `NotFoundError` | No |
| `services/search_sync.py:14-15` | `AsyncElasticsearch`, `NotFoundError`, `async_bulk` | No |
| `services/hybrid_search.py:18` | `AsyncElasticsearch` (type only) | No (takes the client directly) |
| `services/extraction.py`, `pdf_worker.py` | stdlib subprocess/resource; PDF lib in worker | No |

Only the two externally billed/model providers are behind Protocols; ES has none, so tests use a real ES (see `tests/search/test_es_*`).

### B2. Functions over 25 statements (ruff PLR0915, max 25)
- `app/api/uploads.py:59` (40): route-layer function; CLAUDE.md says no business logic in `api/`. Highest priority.
- `app/services/hybrid_search.py:106` (35)
- `app/services/reindex.py:90` (27), `reindex_all`
- `eval/run_eval.py:261` (59, also over the default 50), `eval/lifecycle.py:180` (38), `eval/validate.py:90` (34), `eval/report.py:154` (30)

### B3. PLR0913 (more than 5 args): 8 hits
- `app/db/repositories/chat_messages.py:11` (9 args), `:68` (6)
- `app/db/repositories/documents.py:15` (6)
- `app/db/repositories/tenants.py:68` (6)
- `app/services/search_sync.py:120` (6)
- `eval/lifecycle.py:118` (7), `eval/report.py:333` (8), `eval/run_eval.py:232` (6)

### B4. Behaviour-selecting if/isinstance chains
- `app/services/llm.py:107-117`: six `isinstance(exc, groq.X)` branches mapping to `LLMError` subclasses (returns `(error, retryable)`). A dict keyed by exception type would do; it is also the one place `groq` leaks outside the provider class.
- `app/services/hybrid_search.py:126,134,141`: `isinstance` on `gather(return_exceptions=True)` results (CancelledError / BaseException). Legitimate control flow.
- `app/services/search_sync.py:93`: `isinstance(exc, BulkIndexError | NotFoundError)` picks retry.
- `app/services/documents.py:90,122,143`: `_SAFE_MESSAGE_ERRORS` allow-list decides whether a message is logged.
- No type-switch on a provider/tenant kind anywhere in `app/`.

## C. Dead code and surface

### C1. vulture (`--min-confidence 60`, 31 items in app/)
Almost all false positives (FastAPI route handlers, pydantic `model_config`, validators, settings properties): `api/auth.py:15,36,49`, `api/chat.py:82`, `api/documents.py:94,102,134`, `main.py:46`, `core/config.py:17,85,101`, `db/base.py:14`, all `schemas/*` fields.
Plausibly dead, to verify before removal:
- `app/services/embeddings.py:153` `get_embedding`, `:157` `get_embeddings_batch`
- `app/services/search.py:66` `search_chunks`
- `app/services/es_client.py:50` `es_ready`
- `app/db/repositories/chunks.py:95` `explain_statement` (likely test-only)
- `app/services/pdf_worker.py:17` `ERROR_CODES`
- `app/services/hybrid_search.py:58` `vector_fallback`
- `app/services/chat.py:176` `chat_events` (probably called from the route via name; check)
- `app/services/reindex.py:90` `reindex_all` (called from `scripts/reindex.py`; used)
- `app/db/models/document.py:54` `search_index_error`

### C2. Route table
| Route | Service | Tests (file) | Frontend needs it? |
|---|---|---|---|
| POST /auth/register, /auth/login, GET /auth/me | `services/auth.py` | `tests/auth/test_auth_flow.py`, `test_token_claims.py`, `test_reserved_slug.py` | Yes (login, session) |
| GET/POST /users, GET /users/{id} | `services/users.py` | `tests/isolation/test_users_isolation.py`, `tests/auth/test_users_constraints.py` | Admin only; probably not in v1 UI |
| POST /documents, POST /documents (upload), GET list, GET {id}, GET {id}/chunks, DELETE | `services/documents.py` | `tests/documents/test_documents_*`, `tests/ingestion/*` | Yes (upload/list/delete); `/chunks` debug-only |
| POST /search, /search/keyword, /search/hybrid | `search.py`, `keyword_search.py`, `hybrid_search.py` | `tests/search/test_search_*`, `test_hybrid_*`, `tests/isolation/*search*` | Hybrid yes; the other two are diagnostic |
| POST /chat/stream | `services/chat.py` | `tests/chat/*` | Yes |
| GET /conversations, GET /conversations/{id}/messages | `services/conversations.py` | `tests/chat/test_chat_repos.py`, `test_chat_api.py` | Yes |
| GET /health, GET /health/db | none / `db/health.py` | `tests/core/test_health.py`, `test_health_db.py` | Ops only |

Guard: `tests/security/test_route_auth_coverage.py` enforces auth on every route.

### C3. backend/eval breakdown (excluding `__pycache__`)
- 15 `.py` (2,277 lines), 25 `.md`, 2 `.json`, 1 `.yaml` (`questions.yaml`); `eval/corpus` 104K, `eval/results` 556K.
- Eval tests: `tests/eval/` 14 files, 1,848 lines (vs 2,277 lines of eval code); about 320 test cases (guard 113, plumbing 32, gate_rules 30, cleanup_repository 17 ...).
- `backend/dist/` holds a built wheel and sdist (check it is gitignored).

### C4. app/ references to eval/cleanup logic
- `app/services/auth.py:34` `RESERVED_SLUG_PREFIX = "eval-"`: registration refuses slugs starting `eval-` so the eval harness can own that namespace. Reason: prevents a real tenant from being swept by cleanup.
- `app/db/repositories/tenants.py:77` (tenants a cleanup may remove, by slug regex) and `:175` (which ids still exist). Eval-only queries living in a production repository. Allowed by the get_session rule, but they are the largest eval coupling in `app/`.
- `app/core/config.py:83`, `services/chat.py:213` mention `min_retrieval_score` calibrated by eval; config only.
- No `import eval` anywhere in `app/`.

## D. Production readiness

- **Dockerfile:** none (repo has `docker/postgres/` and `docker-compose.yaml` for postgres + ES only). **CI:** no `.github/`. **Liveness/readiness:** `GET /health` (`app/main.py:41`) and `/health/db` (`:46`, AR-12). Compose has healthchecks for 2 services (`docker-compose.yaml:14,33`). No app container, no readiness probe that checks ES.
- **Unsafe prod defaults:**
  - `config.py:31` `allow_public_registration = True`
  - `config.py:27` `app_env = "local"`, nothing branches on it
  - `config.py:30` `access_token_minutes = 60`, no refresh (AR-08)
  - `config.py:~66` `es_endpoint = http://127.0.0.1:9200`, ES security off in compose (`:26`, AR-04)
  - no rate limiting anywhere (AR-07, AR-13); no CORS config in `main.py`
  - positives: JWT secret placeholder and min length enforced (`config.py:85-93`), secrets are `SecretStr`, ports bound to 127.0.0.1.
- **Memory with embedding model loaded:** peak RSS **256 MB** after one `embed_query` in a fresh process (quantized bge-small ONNX, cache at `backend/.cache/fastembed`). This excludes DB pools, ES client and PDF workers (each capped at 512 MB address space, up to 2 concurrent; `config.py:~43`). Budget about 1 GB per container.
- **pip-audit:** "No known vulnerabilities found."
- **deptry:** 6 findings, all false positives from module-vs-package naming: `python_multipart` (`api/uploads.py:10-11`), `jwt` (`core/security.py:7`, package `pyjwt`), `yaml` (`eval/validate.py:25`, package `pyyaml`), plus DEP002 `asyncpg`/`pyjwt` flagged unused (asyncpg is the driver named in the DSN; pyjwt is imported as `jwt`). Real item: `pyyaml` is only used by `eval/`; check it sits in the right dependency group.
- **Overall coverage:** not measured (no DB). `pytest-cov` is installed (commit 6f2e2db).

### AR entries marked pre-deploy
_Snapshot of 2026-10-17, not kept up to date. The live register is [`docs/review/accepted-risks.md`](../review/accepted-risks.md); where the two differ, the register wins._

| ID | Condition | Status |
|---|---|---|
| AR-07 | login rate limit, "Before public deploy (Day 12)" | Open: no limiter in `app/` |
| AR-08 | refresh tokens, same | Open: single 60 min access token |
| AR-12 | untenanted `get_session` in `/health/db` | Open, unchanged |
| AR-13 | `/search*`, `/chat/stream` rate limit and alias refresh per delete | Open |
| AR-04 | ES security disabled, "Deploy" | Open: compose still `xpack.security.enabled=false` |
| AR-14 | migration 0007 validated CHECK, revisit on populated prod table | Open, applies at first prod migration |
| AR-16 | `app.api.deps` imports sqlalchemy (Day 12) | Open: ignore still in `pyproject.toml:~84` |
| AR-01 | PDF isolation, Docker hardening (Day 12) | Open: no Dockerfile |
| AR-10, AR-18 | provisional retrieval threshold, gate (Day 7) | Open |

Also: `docs/plans/day-05.md` has 1 unchecked item (days 2-4 and 6: 0 unchecked).

## E. Tests

- 99 test files, collected with `-m "slow or not slow"`. Counts per file (top): `tooling/test_guard_bash.py` 166, `eval/test_guard.py` 113, `auth/test_token_claims.py` 40, `chat/test_prompt_delimiters.py` 34, `eval/test_eval_plumbing.py` 32, `tooling/test_gate_checks.py` 31, `eval/test_gate_rules.py` 30, `documents/test_documents_upload.py` 25, `search/test_hybrid_search.py` 23. Full list: `uv run pytest --collect-only -q -m "slow or not slow"`.
- 40 files hold 1-4 tests each (e.g. `chat/test_chat_route_guard.py`, `isolation/test_hermetic_fixture_proof.py`, `acceptance/test_day3_acceptance.py`): merge candidates, but review before touching.
- Overlapping areas to inspect first: `search/test_reindex*.py` (4 files), `ingestion/test_ingestion_*.py` (9 files), `isolation/test_search_*.py` (4 files), `eval/` (14 files, about a third of all test lines but tests tooling, not product).
- **Runtime per file and unique coverage: not measured** (no DB/ES). To produce them once services are up, from `backend/`:
  `uv run pytest -m "slow or not slow" --durations=0 --junitxml=<scratch>/j.xml --cov=app --cov=eval --cov-context=test`
  then per-file runtime from the XML `time` sums, and unique coverage by diffing each file's covered lines (`coverage json --show-contexts`) against the union of all other files. Never run two pytest sessions at once (flock in `tests/conftest.py`).
