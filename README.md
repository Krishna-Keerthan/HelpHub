# HelpHub AI

A multi-tenant support knowledge engine: each company gets an isolated workspace, and (in later stages) an
assistant that answers from that company's own documents and resolved tickets, using hybrid search.

| Part                   | Stack                                                       | Docs                                     |
| ---------------------- | ----------------------------------------------------------- | ---------------------------------------- |
| [backend/](backend/)   | FastAPI, SQLAlchemy (async), Alembic, PostgreSQL + pgvector | [backend/README.md](backend/README.md)   |
| [frontend/](frontend/) | Next.js 16, React 19, TypeScript, Tailwind CSS 4            | [frontend/README.md](frontend/README.md) |

## Quick start

```bash
cp .env.example .env                 # fill in values (see comments)
docker compose up -d --wait          # Postgres on localhost:5433

cd backend
uv sync && uv run alembic upgrade head
uv run fastapi dev app/main.py       # API on :8000, docs at /docs

cd ../frontend
cp .env.example .env.local
npm install && npm run dev           # UI on :3000
```

Then open <http://localhost:3000/platform> to create a workspace, and sign in.

## Status

- **Stage 1 (done):** tenants, users, roles, JWT auth, migrations, tenant isolation tests, web UI for
  sign-in, workspace overview and user management.
- **Next:** Postgres Row-Level Security, then Stage 2 (document ingestion + pgvector).
