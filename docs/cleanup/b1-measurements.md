# Session B measurements (2026-10-17, local WSL2 machine, Postgres 16 in Docker)

## /search latency (exit check B)
Real FastEmbed embedder, uvicorn single process, sequential client, tenant with the 24-document eval corpus (49 chunks), all 40 questions from `eval/questions.yaml` x 5 rounds = 200 requests, k=5, 5 warm-up requests excluded.
- p50 **32 ms**, p95 **44 ms**, max 109 ms (HTTP round trip including query embedding and the fused SQL).
- Not measured: concurrency, a larger corpus, a remote database. Local database, so network latency to Supabase is not included.

## Index size vs the 500 MB free-tier limit (projection, not the demo corpus)
Temp table, 10,000 rows: real corpus chunk text plus 5 random tokens from a 5,000-token vocabulary (so the GIN is not artificially small), random unit 384-d vectors, HNSW m=16 ef_construction=64.
- heap 1,338 B/row, TOAST 2,210 B/row, HNSW 2,049 B/row, GIN(tsvector) 259 B/row, primary key 25 B/row; total **5,880 B/row**.
- At that rate 500 MB holds about 85,000 chunks of this table alone. The GIN index is 4.4% of the total. `documents.raw_text` and other tables are not included.
- Real text will vary in token diversity, so the GIN figure is indicative only.
- The demo corpus itself (51 rows in the table at measurement time): heap 72 KB, HNSW 824 KB (minimum allocation dominates at this size), GIN 136 KB, total 1.54 MB.
