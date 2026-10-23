# Search mode summary (32 answerable eval questions)

Rank is the position of the expected document among distinct documents in the top 10 results (k=10), measured on the local tenant after loading `backend/eval/corpus`. Counts are out of 32.

| Mode | Rank 1 | Top 3 | Top 5 | Missing from top 5 |
|---|---|---|---|---|
| vector | 24 | 28 | 31 | 1 |
| keyword | 21 | 31 | 32 | 0 |
| hybrid | 23 | 31 | 32 | 0 |

Ties in the full-text scores and in vector distances are broken by document title, then chunk position, so these numbers are deterministic: the original local tenant and the rebuilt `eval-cloudflare` tenant (Cloudflare vectors) give exactly the same table and the same ranks below.

Best per measure: rank 1 is vector at 24 (1 ahead of hybrid, 3 ahead of keyword); top 3 is keyword and hybrid, tied at 31 (3 ahead of vector); top 5 is keyword and hybrid, tied at 32 (1 ahead of vector); missing from top 5 is keyword and hybrid, tied at 0 (1 fewer than vector).

Sensitivity to tie-breaking: before the deterministic tie-break, ties were broken by random chunk ids, so the rows depended on the tenant. Two earlier realisations (rank 1 / top 3 / top 5 / missing) were: (1) vector 24/28/31/1, keyword 22/30/32/0, hybrid 24/32/32/0; (2) vector 24/28/31/1, keyword 20/29/31/1, hybrid 23/31/32/0. Vector does not change; keyword moves by 1 to 2 questions and hybrid by 1 on rank 1 and top 3. Read differences of 1 to 2 questions between keyword and hybrid as noise.

Provenance: the vectors behind the original tenant were produced with local fastembed (`BAAI/bge-small-en-v1.5`). Across the 49 chunks they agree with the Cloudflare vectors (`@cf/baai/bge-small-en-v1.5`) to a cosine of at least 0.999998 (median 0.999999).

The five queries in `queries.json` were selected because the modes differ on them. They are examples, not a benchmark.
