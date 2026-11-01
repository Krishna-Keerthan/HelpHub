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

## Isolation stress run (2026-11-01)
`backend/scripts/isolation_stress.py` (not a pytest test; run from `backend/`: `uv run python scripts/isolation_stress.py`, add `--control` for the no-RLS control) runs many concurrent tasks as `helphub_app` on a pool of 5 against the local database. Each task runs a random mix of: read own rows, insert for another tenant (must raise the RLS error), update and delete another tenant's row (must affect 0 rows), and a read with no tenant set on a reused connection (must see 0 rows).
- Run on the real `documents` table: 5 runs, each 10 tenants, 200 tasks (50 in flight), 1000 transactions. Result lines:
```
transactions=1000 reads_checked=410 writes_attempted=590 writes_blocked=590 leaks=0 errors=0
transactions=1000 reads_checked=422 writes_attempted=578 writes_blocked=578 leaks=0 errors=0
transactions=1000 reads_checked=427 writes_attempted=573 writes_blocked=573 leaks=0 errors=0
transactions=1000 reads_checked=396 writes_attempted=604 writes_blocked=604 leaks=0 errors=0
transactions=1000 reads_checked=401 writes_attempted=599 writes_blocked=599 leaks=0 errors=0
```
- Negative control: the same workload on a scratch table without RLS (created and dropped by the script) reported leaks in every run (1000 of 1000), so the script can detect a leak.
- Limits: the earlier spike (2026-10-17, `docs/cleanup/spikes.md`) used 2 tenants and reads only; this run uses 10 tenants and reads plus writes. Local Postgres only, not the hosted database or a hosted pooler. The earlier spike script was never committed. Only `documents` was exercised, with the connection settings of the local engine.
