# Tests

Run from `backend/`: `uv run pytest` (default skips slow), `uv run pytest tests/<dir>` for one domain,
`uv run pytest -m "slow or not slow"` for everything.

| Directory | Belongs here |
|---|---|
| `auth/` | login/registration, tokens, security primitives, tenant context, user constraints |
| `chat/` | chat API, service, gate, repositories, schema, prompt building |
| `documents/` | document API, endpoints, service, upload, schema, multipart |
| `ingestion/` | ingestion pipeline (chunks, retry, transactions, logging) and the chunker |
| `pdf/` | PDF extraction limits and queue behavior |
| `search/` | search API, statements, fusion, modes, exact fallback |
| `llm/` | Groq client and embedding providers |
| `core/` | config, health, schema/migrations, RLS coverage, static hygiene checks |
| `isolation/` | cross-tenant isolation and RLS tests. Its `conftest.py` pins HNSW state per module name (`HERMETIC_MODULES`); keep those module names stable |
| `helpers/` | shared non-test modules (`tests.helpers.*`): fakes and builders |

`conftest.py` at the root holds the shared fixtures. Files that read repo paths via `Path(__file__)`
must account for their directory depth.
