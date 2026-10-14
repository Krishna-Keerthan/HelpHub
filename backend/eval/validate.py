"""Evaluation corpus and question-set checks.

Usage (from backend/):  uv run python -m eval.validate [--fake]

Ingests the corpus through the real services into a throw-away tenant, with its
own Elasticsearch index prefix ``eval-<uuid>-``, checks every question's
evidence, and prints counts. The tenant and the indices are always removed.
``--fake`` uses fake embeddings (no model download). No LLM is ever called.

The tenant is created and deleted with the owner role (MIGRATION_DATABASE_URL),
like the test fixtures do; everything else goes through the app services.
"""

import argparse
import asyncio
import sys
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from elasticsearch import AsyncElasticsearch
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.repositories import chunks as chunks_repo
from app.db.tenant_context import tenant_transaction
from app.services import documents as documents_service
from app.services import es_index
from app.services.embeddings import EmbeddingProvider, FakeEmbeddingProvider
from app.services.es_client import alias_name, get_es

EVAL_DIR = Path(__file__).resolve().parent
VALID_SPLITS = {"dev", "test"}
VALID_CATEGORIES = {"paraphrase", "code", "mixed", "keyword", "near_miss", "off_topic"}
KEYS = {"id", "split", "category", "question", "answerable", "evidence"}
MAX_QUESTION_CHARS = 1000


@dataclass(frozen=True)
class CorpusDoc:
    slug: str
    title: str
    content: str


@dataclass(frozen=True)
class IngestedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    slug: str
    chunk_index: int
    content: str


@dataclass(frozen=True)
class EvalEnv:
    tenant_id: uuid.UUID
    user_id: uuid.UUID


# --- loading and schema --------------------------------------------------------------


def load_corpus(directory: Path) -> list[CorpusDoc]:
    """Every ``*.md`` except INDEX.md: first line ``# Title``, then the body."""
    docs: list[CorpusDoc] = []
    for path in sorted(directory.glob("*.md")):
        if path.name == "INDEX.md":
            continue
        first, _, body = path.read_text().partition("\n")
        if not first.startswith("# "):
            raise ValueError(f"{path.name}: first line must be '# Title'")
        docs.append(CorpusDoc(path.stem, first[2:].strip(), body.strip()))
    return docs


def load_questions(path: Path) -> list[Any]:
    data = yaml.safe_load(path.read_text())
    if data is None:
        return []
    if not isinstance(data, list):
        raise TypeError("questions file must be a YAML list")
    return data


def validate_schema(rows: Sequence[Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        where = f"item {index}"
        if not isinstance(row, dict):
            errors.append(f"{where}: must be a mapping")
            continue
        where = f"item {index} ({row.get('id', '?')})"
        for key in sorted(KEYS - row.keys()):
            errors.append(f"{where}: missing key {key}")
        for key in sorted(row.keys() - KEYS):
            errors.append(f"{where}: unknown key {key}")
        qid = row.get("id")
        if isinstance(qid, str) and qid:
            if qid in seen:
                errors.append(f"{where}: duplicate id")
            seen.add(qid)
        elif "id" in row:
            errors.append(f"{where}: id must be a non-empty string")
        if "split" in row and row["split"] not in VALID_SPLITS:
            errors.append(f"{where}: split must be one of {sorted(VALID_SPLITS)}")
        if "category" in row and row["category"] not in VALID_CATEGORIES:
            errors.append(
                f"{where}: category must be one of {sorted(VALID_CATEGORIES)}"
            )
        question = row.get("question")
        if "question" in row and not (
            isinstance(question, str)
            and 1 <= len(question.strip()) <= MAX_QUESTION_CHARS
        ):
            errors.append(
                f"{where}: question must be 1..{MAX_QUESTION_CHARS} characters"
            )
        answerable = row.get("answerable")
        if "answerable" in row and not isinstance(answerable, bool):
            errors.append(f"{where}: answerable must be true or false")
        evidence = row.get("evidence")
        if "evidence" in row:
            if not isinstance(evidence, list) or not all(
                isinstance(e, str) and e for e in evidence
            ):
                errors.append(f"{where}: evidence must be a list of non-empty strings")
            elif answerable is True and not evidence:
                errors.append(f"{where}: evidence must not be empty when answerable")
            elif answerable is False and evidence:
                errors.append(f"{where}: evidence must be empty when not answerable")
    return errors


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(rows),
        "category": dict(sorted(Counter(r["category"] for r in rows).items())),
        "split": dict(sorted(Counter(r["split"] for r in rows).items())),
    }


# --- evidence --------------------------------------------------------------------------


def check_evidence(
    rows: Sequence[dict[str, Any]], chunks: Sequence[IngestedChunk]
) -> list[str]:
    """Each evidence snippet must occur in exactly one chunk."""
    errors: list[str] = []
    for row in rows:
        for snippet in row["evidence"]:
            matches = sum(1 for c in chunks if snippet in c.content)
            if matches == 0:
                errors.append(f"{row['id']}: evidence {snippet!r} matches no chunk")
            elif matches > 1:
                errors.append(
                    f"{row['id']}: evidence {snippet!r} matches {matches} chunks"
                )
    return errors


def relevant_ids(
    row: dict[str, Any], chunks: Sequence[IngestedChunk]
) -> set[uuid.UUID]:
    """Chunks containing any of the question's evidence snippets."""
    return {
        c.chunk_id
        for c in chunks
        if any(snippet in c.content for snippet in row["evidence"])
    }


# --- throw-away tenant and index prefix -----------------------------------------------


def _owner_engine() -> Any:
    return create_async_engine(settings.migration_database_url, poolclass=NullPool)


async def _create_tenant() -> EvalEnv:
    slug = f"eval-{uuid.uuid4().hex[:12]}"
    engine = _owner_engine()
    try:
        async with engine.begin() as conn:
            tenant_id = (
                await conn.execute(
                    text(
                        "INSERT INTO tenants (slug, name) VALUES (:s, :s) RETURNING id"
                    ),
                    {"s": slug},
                )
            ).scalar_one()
            user_id = (
                await conn.execute(
                    text(
                        "INSERT INTO users (tenant_id, email, password_hash, role, is_active) "
                        "VALUES (:t, :e, 'unusable', 'admin', false) RETURNING id"
                    ),
                    {"t": tenant_id, "e": f"eval@{slug}.example.com"},
                )
            ).scalar_one()
        return EvalEnv(tenant_id, user_id)
    finally:
        await engine.dispose()


async def _delete_tenant(tenant_id: uuid.UUID) -> None:
    engine = _owner_engine()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id}
            )
    finally:
        await engine.dispose()


async def _delete_indices(es: AsyncElasticsearch, prefix: str) -> None:
    found = await es.indices.get(
        index=f"{prefix}*", ignore_unavailable=True, allow_no_indices=True
    )
    if found:
        await es.indices.delete(index=list(found), ignore_unavailable=True)


@asynccontextmanager
async def eval_environment(es: AsyncElasticsearch) -> AsyncIterator[EvalEnv]:
    """A dedicated tenant and ``eval-<uuid>-`` index prefix; always cleaned up."""
    previous_prefix = settings.es_index_prefix
    prefix = f"eval-{uuid.uuid4().hex[:12]}-"
    env: EvalEnv | None = None
    settings.es_index_prefix = prefix
    es_index.reset_ensure_cache()
    try:
        env = await _create_tenant()
        yield env
    finally:
        try:
            await _delete_indices(es, prefix)
        finally:
            try:
                if env is not None:
                    await _delete_tenant(env.tenant_id)
            finally:
                es_index.reset_ensure_cache()
                settings.es_index_prefix = previous_prefix


async def ingest_corpus(
    env: EvalEnv,
    docs: Sequence[CorpusDoc],
    provider: EmbeddingProvider,
    es: AsyncElasticsearch,
) -> list[IngestedChunk]:
    """Create, embed, store and index every document; return all its chunks."""
    chunks: list[IngestedChunk] = []
    for doc in docs:
        document, _ = await documents_service.create_or_get(
            env.tenant_id, env.user_id, doc.title, doc.content
        )
        await documents_service.ingest_document(
            env.tenant_id, document.id, provider, es
        )
        async with tenant_transaction(env.tenant_id) as session:
            rows = await chunks_repo.list_for_indexing(
                session, env.tenant_id, document.id
            )
        chunks.extend(
            IngestedChunk(chunk_id, document.id, doc.slug, index, content)
            for chunk_id, index, content in rows
        )
    await es.indices.refresh(index=alias_name())
    return chunks


# --- command line -----------------------------------------------------------------------


async def run(use_fake: bool) -> int:
    docs = load_corpus(EVAL_DIR / "corpus")
    rows = load_questions(EVAL_DIR / "questions.yaml")
    errors = validate_schema(rows)
    es = get_es()
    provider: EmbeddingProvider
    if use_fake:
        provider = FakeEmbeddingProvider()
    else:
        from app.services.embeddings import default_provider

        provider = default_provider()
    try:
        async with eval_environment(es) as env:
            chunks = await ingest_corpus(env, docs, provider, es)
            if not errors:
                errors += check_evidence(rows, chunks)
            print(f"documents: {len(docs)}  chunks: {len(chunks)}")
    finally:
        await es.close()
    summary = summarize(rows) if not errors else {"total": len(rows)}
    print(f"questions: {summary}")
    for error in errors:
        print(f"ERROR {error}")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake", action="store_true", help="fake embeddings")
    return asyncio.run(run(parser.parse_args().fake))


if __name__ == "__main__":
    sys.exit(main())
