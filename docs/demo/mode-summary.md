# Search mode summary (32 answerable eval questions)

Rank is the position of the expected document among distinct documents in the top 10 results (k=10), measured on the local tenant after loading `backend/eval/corpus`. Counts are out of 32.

| Mode | Rank 1 | Top 3 | Top 5 | Missing from top 5 |
|---|---|---|---|---|
| vector | 24 | 28 | 31 | 1 |
| keyword | 22 | 30 | 32 | 0 |
| hybrid | 24 | 32 | 32 | 0 |

Provenance: the vectors behind these numbers were produced with local fastembed (`BAAI/bge-small-en-v1.5`). Across the 49 chunks they agree with the Cloudflare vectors (`@cf/baai/bge-small-en-v1.5`) to a cosine of at least 0.999998 (median 0.999999).

Best per measure: rank 1 is vector and hybrid, tied at 24 (2 ahead of keyword); top 3 is hybrid at 32 (2 ahead of keyword, 4 ahead of vector); top 5 is keyword and hybrid, tied at 32 (1 ahead of vector); missing from top 5 is keyword and hybrid, tied at 0 (1 fewer than vector).

The five queries in `queries.json` were selected because the modes differ on them. They are examples, not a benchmark.
