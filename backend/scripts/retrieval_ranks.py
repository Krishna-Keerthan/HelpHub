"""Per-question rank of the expected document for vector, keyword and hybrid search.

Read-only: runs the real search code against a tenant that already holds the eval
corpus (see load_demo_corpus.py). Rank is the position of the expected document among
distinct documents in the top 10 results (k=10). Prints Recall@1/3/5, MRR@10, the 95%
Wilson interval for Recall@5, and one rank per question per mode ("-" = not in top 10).
Refuses to run unless both database URLs are local. Prints no document text.

Run from backend/:  uv run python scripts/retrieval_ranks.py [tenant-slug]
The slug defaults to local-dev. The embedding provider is the one in settings.
"""

import argparse
import asyncio
import sys
import uuid

from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine
from app.db.tenant_context import tenant_transaction
from app.services.embeddings import default_provider
from app.services.search import search
from eval.records import MODES
from eval.stats import wilson_interval
from eval.validate import EVAL_DIR, load_questions
from tests.helpers.db_guard import current_refusal

K = 10


async def run(slug: str) -> int:
    provider = default_provider()
    async with engine.connect() as connection:
        found = (
            await connection.execute(
                text("SELECT id FROM tenants WHERE slug = :s"), {"s": slug}
            )
        ).scalar_one_or_none()
    if found is None:
        print("tenant not found", file=sys.stderr)
        return 1
    tenant_id: uuid.UUID = found
    async with tenant_transaction(tenant_id) as session:
        chunks = (
            await session.execute(text("SELECT document_id, text FROM chunks"))
        ).all()
        n_docs = (
            await session.execute(text("SELECT count(*) FROM documents"))
        ).scalar_one()
    questions = [
        r for r in load_questions(EVAL_DIR / "questions.yaml") if r["answerable"]
    ]
    ranks: dict[str, list[int | None]] = {mode: [] for mode in MODES}
    for row in questions:
        expected = {
            doc for doc, body in chunks if any(e in body for e in row["evidence"])
        }
        if not expected:
            print(f"{row['id']}: evidence not found in the tenant", file=sys.stderr)
            return 1
        for mode in MODES:
            hits = await search(tenant_id, row["question"], K, provider, mode)
            distinct: list[uuid.UUID] = []
            for hit in hits:
                if hit.hit.document_id not in distinct:
                    distinct.append(hit.hit.document_id)
            ranks[mode].append(
                next((i for i, d in enumerate(distinct, 1) if d in expected), None)
            )
    n = len(questions)
    print(
        f"provider={settings.embedding_provider} model={provider.model_name} "
        f"documents={n_docs} chunks={len(chunks)} questions={n}"
    )
    for mode, values in ranks.items():
        at = {k: sum(1 for r in values if r is not None and r <= k) for k in (1, 3, 5)}
        mrr = sum(1 / r for r in values if r) / n
        low, high = wilson_interval(at[5], n)
        print(
            f"{mode}: R@1={at[1]}/{n} R@3={at[3]}/{n} R@5={at[5]}/{n} "
            f"MRR@10={mrr:.3f} wilson95_R@5=[{low:.3f},{high:.3f}]"
        )
    print("question " + " ".join(MODES))
    for i, row in enumerate(questions):
        print(row["id"], *(ranks[m][i] or "-" for m in MODES))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("slug", nargs="?", default="local-dev")
    args = parser.parse_args()
    refusal = current_refusal()
    if refusal:
        print(refusal, file=sys.stderr)
        return 3

    async def go() -> int:
        try:
            return await run(args.slug)
        finally:
            await engine.dispose()

    return asyncio.run(go())


if __name__ == "__main__":
    raise SystemExit(main())
