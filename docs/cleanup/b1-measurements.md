# Session B measurements (2026-10-17, local WSL2 machine, Postgres 16 in Docker)

## /search latency (exit check B)
Real FastEmbed embedder, uvicorn single process, sequential client, tenant with the 24-document eval corpus (49 chunks), all 40 questions from `eval/questions.yaml` x 5 rounds = 200 requests, k=5, 5 warm-up requests excluded.
- p50 **32 ms**, p95 **44 ms**, max 109 ms (HTTP round trip including query embedding and the fused SQL).
- Not measured: concurrency, a larger corpus, a remote database. Local database, so network latency to Supabase is not included.

## Index size vs the 500 MB free-tier limit (projection, not the demo corpus)
Temp table, 10,000 rows: real corpus chunk text plus 5 random tokens from a 5,000-token vocabulary (so the GIN is not artificially small), random unit 384-d vectors, HNSW m=16 ef_construction=64.
- heap 1,338 B/row, TOAST 2,210 B/row, HNSW 2,049 B/row, GIN(tsvector) 259 B/row, primary key 25 B/row; total **5,880 B/row**.
- At that rate 500 MB holds about 85,000 chunks of this table alone. The GIN index is 4.4% of the total. `documents.raw_text` and other tables are not included in that 5,880 B figure (see the correction below).
- Real text will vary in token diversity, so the GIN figure is indicative only.
- The demo corpus itself (51 rows in the table at measurement time): heap 72 KB, HNSW 824 KB (minimum allocation dominates at this size), GIN 136 KB, total 1.54 MB.

### Correction (Session C, C1b): the `documents` table
The 5,880 B/row above is the `chunks` table only. Measured separately: the 24 eval-corpus documents replicated to 10,008 rows in a temp copy of `documents` (`LIKE documents INCLUDING ALL`, so its indexes are included), 20,433 chunks' worth (49 chunks per 24 documents, from `chunk_text` defaults): `raw_text` stored 654 B/chunk (average document 1.3 KB, so almost nothing is compressed), and `documents` heap + TOAST + indexes **925 B/chunk**.
- Projection with both tables: 5,880 + 925 = **6,805 B/chunk**, so 500 MB holds about **73,000 chunks**, not 85,000.
- The ratio depends on chunks per document (2.04 here). Long documents cost about one chunk's worth of `raw_text` per chunk. `users`, `conversations`, `chat_messages` and `alembic_version` are still not included.
