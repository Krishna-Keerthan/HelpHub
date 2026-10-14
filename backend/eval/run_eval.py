"""Retrieval evaluation: vector vs keyword vs hybrid on the Acme corpus.

Usage (from backend/):
    uv run python -m eval.run_eval [--keep] [--no-ablation] [--baseline] [--out FILE]

Takes the shared database lock (refuses if held), validates the question set,
creates a dedicated eval tenant through the real registration service and an
``eval-<uuid>-`` Elasticsearch prefix, ingests the corpus with the real FastEmbed
model, and calls the search SERVICES (never HTTP) under that tenant. Always
cleans up in ``finally`` and prints leak counts. No LLM is called.
"""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import secrets
import subprocess
import sys
import time
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import elasticsearch
from sqlalchemy import text

from app.core.config import settings
from app.db.repositories import chunks as chunks_repo
from app.db.session import AsyncSessionLocal
from app.db.tenant_context import tenant_transaction
from app.schemas.auth import RegisterRequest
from app.services import auth as auth_service
from app.services import chunker, es_index, hybrid_search, keyword_search
from app.services.embeddings import EmbeddingProvider, default_provider
from app.services.es_client import alias_name, get_es
from app.services.search import search_in_session
from eval import analysis, cleanup, integrity, report, validate
from eval.guard import GuardedEs, assert_eval_prefix
from eval.lock import LockHeld, hold_lock
from eval.records import Ranking, Record, to_json

EVAL_DIR = Path(__file__).resolve().parent
REPO = EVAL_DIR.parents[1]
WARMUPS = 3
TOP = 10
CANDIDATES = 50


@dataclass
class Env:
    tenant_id: uuid.UUID
    user_id: uuid.UUID


def write_files(files: dict[Path, str]) -> None:
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def _git(*args: str) -> str:
    return subprocess.run(  # noqa: S603 - fixed git arguments
        ["git", *args],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def _db_environment() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        pgvector = (
            await session.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
        ).scalar_one()
        index_def = (
            await session.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"),
                {"n": chunks_repo.CHUNKS_EMBEDDING_INDEX},
            )
        ).scalar_one()
    return {
        "pgvector": pgvector,
        "hnsw_index": index_def.split(" USING ", 1)[-1],
        "hnsw_ef_search": f"max({chunks_repo.MIN_EF_SEARCH}, k), capped at {chunks_repo.MAX_EF_SEARCH}",
        "hnsw_iterative_scan": "relaxed_order",
    }


async def environment(
    es: Any, provider: EmbeddingProvider, n_docs: int, n_chunks: int
) -> dict[str, Any]:
    info = await es.info()
    dirty = _git("status", "--porcelain", "--untracked-files=no")
    untracked = _git("ls-files", "--others", "--exclude-standard")
    corpus = {
        p.name: _sha256(p)[:16] for p in sorted((EVAL_DIR / "corpus").glob("*.md"))
    }
    env: dict[str, Any] = {
        "git_sha": _git("rev-parse", "HEAD")[:12],
        "dirty (tracked modifications only)": "yes" if dirty else "no",
        "untracked files": untracked.replace("\n", ", ") or "none",
        "elasticsearch server": info["version"]["number"],
        "elasticsearch client": elasticsearch.__version__,
        **await _db_environment(),
        "embedding model": provider.model_name,
        "documents": n_docs,
        "chunks": n_chunks,
        "chunker": f"max_chars={chunker.DEFAULT_MAX_CHARS}, overlap={chunker.DEFAULT_OVERLAP}",
        "rrf_k": settings.rrf_k,
        "hybrid_candidates": settings.hybrid_candidates,
        "min_retrieval_score (unchanged)": settings.min_retrieval_score,
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "machine": f"{platform.system()} {platform.release()} {platform.machine()}",
        "questions.yaml sha256": _sha256(EVAL_DIR / "questions.yaml"),
        "corpus files sha256 (first 16)": ", ".join(
            f"{k}={v}" for k, v in corpus.items()
        ),
    }
    return env


async def create_env() -> Env:
    slug = f"eval-{uuid.uuid4().hex[:12]}"
    user, _ = await auth_service.register_tenant(
        RegisterRequest(
            tenant_name=slug,
            tenant_slug=slug,
            email=f"eval@{slug}.example.com",
            password=secrets.token_urlsafe(24),
        )
    )
    return Env(user.tenant_id, user.id)


async def _timed_vector(
    env: Env, provider: EmbeddingProvider, query: str, k: int
) -> tuple[Ranking, bool, float]:
    started = time.perf_counter()
    embedding = await provider.embed_query(query)
    async with tenant_transaction(env.tenant_id) as session:
        result = await search_in_session(session, env.tenant_id, embedding, k)
    elapsed = (time.perf_counter() - started) * 1000
    ranking = Ranking([h.chunk_id for h in result.hits], [h.score for h in result.hits])
    return ranking, result.used_fallback, elapsed


async def _timed_keyword(
    env: Env, es: Any, query: str, k: int
) -> tuple[Ranking, float]:
    started = time.perf_counter()
    hits = await keyword_search.search(env.tenant_id, query, k, es)
    elapsed = (time.perf_counter() - started) * 1000
    return Ranking([h.hit.chunk_id for h in hits], [h.hit.score for h in hits]), elapsed


async def _timed_hybrid(
    env: Env, es: Any, provider: EmbeddingProvider, query: str
) -> tuple[Ranking, list[str], float]:
    started = time.perf_counter()
    result = await hybrid_search.hybrid_search(env.tenant_id, query, TOP, provider, es)
    elapsed = (time.perf_counter() - started) * 1000
    ranking = Ranking(
        [h.chunk_id for h in result.hits], [h.rrf_score for h in result.hits]
    )
    return ranking, list(result.degraded), elapsed


async def measure(
    env: Env,
    es: Any,
    provider: EmbeddingProvider,
    rows: list[dict[str, Any]],
    chunks: list[validate.IngestedChunk],
) -> tuple[list[Record], list[str]]:
    degraded: list[str] = []
    for row in rows[:WARMUPS]:  # discarded
        await _timed_vector(env, provider, row["question"], TOP)
        await _timed_keyword(env, es, row["question"], TOP)
        await _timed_hybrid(env, es, provider, row["question"])
    records: list[Record] = []
    for row in rows:
        q = row["question"]
        vector, fallback, t_v = await _timed_vector(env, provider, q, TOP)
        keyword, t_k = await _timed_keyword(env, es, q, TOP)
        hybrid, miss, t_h = await _timed_hybrid(env, es, provider, q)
        if miss:
            degraded.append(f"{row['id']}: degraded {miss}")
        branch_v, _, _ = await _timed_vector(env, provider, q, CANDIDATES)
        branch_k, _ = await _timed_keyword(env, es, q, CANDIDATES)
        records.append(
            Record(
                id=row["id"],
                split=row["split"],
                category=row["category"],
                answerable=row["answerable"],
                question=q,
                relevant=validate.relevant_ids(row, chunks)
                if row["answerable"]
                else set(),
                modes={"vector": vector, "keyword": keyword, "hybrid": hybrid},
                branches={"vector": branch_v, "keyword": branch_k},
                fallback=fallback,
                latency_ms={"vector": t_v, "keyword": t_k, "hybrid": t_h},
            )
        )
    return records, degraded


def snippet_matches(
    rows: list[dict[str, Any]], chunks: list[validate.IngestedChunk]
) -> dict[str, int]:
    """Per question: the smallest number of chunks any one evidence snippet hits."""
    out: dict[str, int] = {}
    for row in rows:
        if row["answerable"]:
            out[row["id"]] = min(
                sum(1 for c in chunks if s in c.content) for s in row["evidence"]
            )
    return out


async def teardown(
    *,
    keep: bool,
    prefix: str,
    tenant_id: uuid.UUID | None,
    raw_es: Any,
    es: Any,
    delete_tenant: Callable[[uuid.UUID], Awaitable[None]],
) -> None:
    """Remove the eval indices, then the tenant (cascade), unless ``keep``.

    The tenant is deleted even when the index deletion fails.
    """
    if keep:
        print(f"--keep: tenant {tenant_id}, prefix {prefix} retained")
        return
    try:
        found = await raw_es.indices.get(
            index=f"{prefix}*", ignore_unavailable=True, allow_no_indices=True
        )
        if found:
            await es.indices.delete(index=list(found), ignore_unavailable=True)
    finally:
        if tenant_id is not None:
            await delete_tenant(tenant_id)


async def leak_counts(es: Any, tenant_id: uuid.UUID | None) -> dict[str, int]:
    tenants = len(await cleanup.eval_tenants())
    found = await es.indices.get(
        index="eval-*", ignore_unavailable=True, allow_no_indices=True
    )
    chunk_rows = 0
    if tenant_id is not None:
        async with tenant_transaction(tenant_id) as session:
            chunk_rows = (
                await session.execute(text("SELECT count(*) FROM chunks"))
            ).scalar_one()
    return {
        "eval tenants": tenants,
        "eval indices": len(found),
        "chunk rows": chunk_rows,
    }


def print_summary(
    env: dict[str, Any],
    records: list[Record],
    checks: dict[str, list[str]],
    extra: dict[str, Any],
    leaks: dict[str, int],
    out: Path,
) -> None:
    lines = [
        f"sha {env['git_sha']}  dirty={env['dirty (tracked modifications only)']}  model={env['embedding model']}"
    ]
    lines.append("hit@5 (answerable, count = % ):  split  vector | keyword | hybrid")
    for split in report.SPLITS:
        cells = []
        for mode in ("vector", "keyword", "hybrid"):
            a = analysis.aggregate(records, mode, split=split)
            cells.append(f"{a.hit5}/{a.n}")
        lines.append(f"  {split:5} " + " | ".join(cells))
    for name, problems in checks.items():
        lines.append(
            f"integrity {name}: {'PASS' if not problems else 'FAIL ' + '; '.join(problems[:2])}"
        )
    lines.append(f"gate recommendation: {extra['gate_recommendation'] or 'none'}")
    lines.append(f"ablation decision: {extra['ablation_decision']}")
    lines.append(f"leaks after cleanup: {leaks}")
    lines.append(f"report: {out}")
    print("\n".join(lines[:40]))


async def run(
    keep: bool, with_ablation: bool, baseline: bool, out: Path, results_dir: Path
) -> int:
    rows = validate.load_questions(EVAL_DIR / "questions.yaml")
    errors = validate.validate_schema(rows)
    if errors:
        print("questions.yaml FAILED validation (not edited):")
        print("\n".join(errors[:20]))
        return 1
    docs = validate.load_corpus(EVAL_DIR / "corpus")
    previous_prefix = settings.es_index_prefix
    prefix = f"eval-{uuid.uuid4().hex[:12]}-"
    raw_es = get_es()
    es: Any = GuardedEs(raw_es)
    settings.es_index_prefix = prefix
    es_index.reset_ensure_cache()
    assert_eval_prefix()
    env: Env | None = None
    status = 0
    try:
        removed = await cleanup.cleanup(es)
        if any(removed):
            print(f"startup cleanup removed tenants={removed[0]} indices={removed[1]}")
        provider = default_provider()
        await provider.warm_up()
        env = await create_env()
        # Harness only: no automatic refresh while ingesting, so the corpus lands in
        # one segment in ingestion order (ingest_corpus refreshes once at the end).
        # Exactly tied BM25 scores then keep the same order in every run.
        await es_index.ensure_index(es)
        await es.indices.put_settings(
            index=alias_name(), settings={"index": {"refresh_interval": "-1"}}
        )
        chunks = await validate.ingest_corpus(env, docs, provider, es)  # type: ignore[arg-type]
        if errors := validate.check_evidence(rows, chunks):
            print("evidence FAILED (questions not edited):\n" + "\n".join(errors[:20]))
            return 1
        indexed = (await raw_es.count(index=alias_name()))["count"]
        records, degraded = await measure(env, es, provider, rows, chunks)
        categories = dict(Counter(r["category"] for r in rows))
        checks = {
            "hybrid == fuse_rrf(branches)": integrity.check_fusion(
                records, settings.rrf_k
            ),
            "evidence resolves": integrity.check_evidence_resolves(
                snippet_matches(rows, chunks)
            ),
            "answerable have relevant chunks": integrity.check_relevance(records),
            "splits 24/16 and categories": integrity.check_splits(records, categories),
            "ES chunk count == DB chunk count": []
            if indexed == len(chunks)
            else [f"{indexed} != {len(chunks)}"],
            "no degraded branch": degraded,
        }
        contents = {c.chunk_id: c.content for c in chunks}
        environment_block = await environment(raw_es, provider, len(docs), len(chunks))
        text_md, extra = report.render(
            date=datetime.now(UTC).strftime("%Y-%m-%d"),
            env=environment_block, records=records, contents=contents,
            n_docs=len(docs), checks=checks, warmups=WARMUPS, with_ablation=with_ablation,
        )  # fmt: skip
        payload = json.dumps(
            {
                "env": environment_block, "checks": checks, **extra,
                "chunks": {str(c.chunk_id): {"slug": c.slug, "index": c.chunk_index, "content": c.content} for c in chunks},
                "records": [to_json(r) for r in records],
            },
            indent=1, sort_keys=True, default=str,
        )  # fmt: skip
        files = {
            out: text_md,
            results_dir / f"{environment_block['git_sha']}.json": payload,
        }
        if baseline:
            files[results_dir / "baseline.json"] = payload
        await asyncio.to_thread(write_files, files)
        failed = [n for n, p in checks.items() if p]
        if failed:
            print("INTEGRITY CHECKS FAILED: " + ", ".join(failed))
            status = 1
        summary = (environment_block, records, checks, extra, out)
    finally:
        leaks: dict[str, int] = {}
        try:
            await teardown(
                keep=keep,
                prefix=prefix,
                tenant_id=env.tenant_id if env else None,
                raw_es=raw_es,
                es=es,
                delete_tenant=cleanup.delete_tenant,
            )
            leaks = await leak_counts(
                raw_es, None if keep else (env.tenant_id if env else None)
            )
            if not keep and any(leaks.values()):
                print(f"G14: eval cleanup incomplete: {leaks}")
                status = 3
        finally:
            es_index.reset_ensure_cache()
            settings.es_index_prefix = previous_prefix
            await raw_es.close()
    if "summary" in locals():
        print_summary(summary[0], summary[1], summary[2], summary[3], leaks, summary[4])
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep", action="store_true", help="keep the eval tenant and indices"
    )
    parser.add_argument("--no-ablation", action="store_true")
    parser.add_argument(
        "--baseline", action="store_true", help="also write results/baseline.json"
    )
    parser.add_argument(
        "--out", type=Path, default=REPO / "docs" / "eval" / "latest.md"
    )
    parser.add_argument("--results-dir", type=Path, default=EVAL_DIR / "results")
    args = parser.parse_args()
    try:
        with hold_lock():
            return asyncio.run(
                run(
                    args.keep,
                    not args.no_ablation,
                    args.baseline,
                    args.out,
                    args.results_dir,
                )
            )
    except LockHeld as exc:
        print(f"refusing to start: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
