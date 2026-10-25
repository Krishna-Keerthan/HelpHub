"""Ties are broken by document title then chunk position, not by random ids."""

import importlib.util
from pathlib import Path

import pytest

from app.services import documents as documents_service
from app.services.embeddings import FakeEmbeddingProvider
from app.services.search import search
from eval.validate import load_questions

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval_gate.py"
spec = importlib.util.spec_from_file_location("eval_gate", SCRIPT)
assert spec and spec.loader
eg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eg)


async def _load(tenant, corpus) -> None:
    provider = FakeEmbeddingProvider()
    for title, content in corpus:
        document, _ = await documents_service.create_or_get(
            tenant["id"], tenant["user_id"], title, content
        )
        await documents_service.ingest_document(tenant["id"], document.id, provider)


@pytest.mark.parametrize("mode", ["hybrid", "vector", "keyword"])
async def test_same_corpus_different_insertion_order_gives_identical_rankings(
    make_tenant, mode: str
) -> None:
    corpus = await eg.corpus_texts()
    first, second = await make_tenant(), await make_tenant()
    await _load(first, corpus)
    await _load(second, list(reversed(corpus)))
    provider = FakeEmbeddingProvider()
    questions = [r["question"] for r in load_questions(eg.QUESTIONS) if r["answerable"]]
    assert len(questions) == 32
    for question in questions:
        ranked = []
        for tenant in (first, second):
            hits = await search(tenant["id"], question, 10, provider, mode)  # type: ignore[arg-type]
            assert hits
            ranked.append([(h.document_title, h.hit.chunk_index) for h in hits])
            assert {h.hit.document_id for h in hits} <= {
                d.id
                for d in await documents_service.list_documents(tenant["id"], limit=200)
            }
        assert ranked[0] == ranked[1], question
