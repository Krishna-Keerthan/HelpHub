# Deploy runbook (Render + Supabase)

## Connection defaults
- Both the app (`DATABASE_URL`) and migrations (`MIGRATION_DATABASE_URL`) use the Supabase **session pooler**, port 5432, username `role.<project-ref>`. Measured working with no asyncpg changes (spikes.md section 1).
- If the app is ever moved to the transaction pooler (port 6543), set asyncpg `statement_cache_size=0` in `app/db/session.py`; without it 174 of 180 test transactions failed with SQLSTATE 26000.
- Migrations run only as `helphub_owner`, never as `postgres` (otherwise Supabase grants the API roles access to new tables; spikes.md section 4).

## Supabase role setup (once, as `postgres` over the session pooler)
Pooler usernames are `role.<project-ref>`. `postgres` is not a superuser (CREATEROLE, BYPASSRLS).
```
CREATE ROLE helphub_owner LOGIN PASSWORD '...' NOSUPERUSER NOBYPASSRLS;
CREATE ROLE helphub_app   LOGIN PASSWORD '...' NOSUPERUSER NOBYPASSRLS;
GRANT helphub_owner TO postgres;              -- required for ALTER DEFAULT PRIVILEGES FOR ROLE helphub_owner
GRANT CONNECT, CREATE ON DATABASE postgres TO helphub_owner;
GRANT CONNECT ON DATABASE postgres TO helphub_app;
GRANT USAGE, CREATE ON SCHEMA public TO helphub_owner;
GRANT USAGE ON SCHEMA public TO helphub_app;
ALTER DEFAULT PRIVILEGES FOR ROLE helphub_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO helphub_app;
ALTER DEFAULT PRIVILEGES FOR ROLE helphub_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO helphub_app;
```
Do not rotate a role's password repeatedly while connecting through the pooler: the pooler kept rejecting the new password and repeated failures tripped its circuit breaker (`ECIRCUITBREAKER`, all new connections blocked for minutes).

## Open items
- [ ] **Render IPv6 to Supabase direct connection: unknown.** Not testable from the dev box. Until answered, do not use the direct host (`db.<ref>.supabase.co`); stay on the session pooler. Test on the first Render deploy and record the result here.
