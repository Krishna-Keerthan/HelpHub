"""Evaluation plumbing: metrics, schema checks, corpus sanity, and a 3-document
end-to-end ingest (mechanics only: fake embeddings, real Postgres and Elasticsearch)."""

import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services import hybrid_search
from app.services.embeddings import FakeEmbeddingProvider
from app.services.es_client import get_es
from eval import metrics, validate

EVAL_DIR = Path(validate.__file__).resolve().parent
A, B, C, D = (uuid.UUID(int=i) for i in range(1, 5))


# --- metrics (toy data) ------------------------------------------------------------


def test_hit_at_k() -> None:
    assert metrics.hit_at_k([A, B, C], {C}, 3) == 1.0
    assert metrics.hit_at_k([A, B, C], {C}, 2) == 0.0
    assert metrics.hit_at_k([A, B, C], {D}, 3) == 0.0
    assert metrics.hit_at_k([], {A}, 3) == 0.0


def test_mrr_at_k() -> None:
    assert metrics.mrr_at_k([A, B, C], {A}, 3) == 1.0
    assert metrics.mrr_at_k([A, B, C], {B, C}, 3) == 0.5  # first relevant at rank 2
    assert metrics.mrr_at_k([A, B, C], {C}, 2) == 0.0  # beyond the cut-off
    assert metrics.mrr_at_k([A, B, C], {D}, 3) == 0.0


def test_recall_at_k() -> None:
    assert metrics.recall_at_k([A, B, C], {A, C}, 3) == 1.0
    assert metrics.recall_at_k([A, B, C], {A, C}, 2) == 0.5
    assert metrics.recall_at_k([A, B], {C, D}, 2) == 0.0
    with pytest.raises(ValueError):
        metrics.recall_at_k([A], set(), 1)


@pytest.mark.parametrize("k", [0, -1])
def test_k_must_be_positive(k: int) -> None:
    with pytest.raises(ValueError):
        metrics.hit_at_k([A], {A}, k)


def test_duplicate_ids_in_a_ranking_count_once() -> None:
    assert metrics.recall_at_k([A, A, B], {A, B}, 3) == 1.0
    assert metrics.recall_at_k([A, A, B], {A, B}, 2) == 1.0  # A, B after dedupe
    assert metrics.recall_at_k([A, A, B], {A, B}, 1) == 0.5


def test_percentiles_use_linear_interpolation() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert metrics.percentiles(values, [0, 50, 100]) == {0: 10.0, 50: 30.0, 100: 50.0}
    assert metrics.percentiles(values, [25]) == {25: 20.0}
    assert metrics.percentiles([7.0], [50, 95]) == {50: 7.0, 95: 7.0}
    assert metrics.percentiles([4.0, 1.0, 3.0, 2.0], [50]) == {
        50: 2.5
    }  # unsorted input
    with pytest.raises(ValueError):
        metrics.percentiles([], [50])
    with pytest.raises(ValueError):
        metrics.percentiles([1.0], [101])


def test_mean() -> None:
    assert metrics.mean([1.0, 0.0, 0.5]) == pytest.approx(0.5)
    assert metrics.mean([]) == 0.0


# --- question schema ---------------------------------------------------------------


def _row(**overrides: object) -> dict:
    row = {
        "id": "dev-001",
        "split": "dev",
        "category": "code",
        "question": "What does E-4012 mean?",
        "answerable": True,
        "evidence": ["Assertion signature invalid"],
    }
    return {**row, **overrides}


def test_valid_rows_and_empty_list_pass() -> None:
    assert validate.validate_schema([]) == []
    assert validate.validate_schema([_row()]) == []
    off = _row(
        id="t-1", split="test", category="off_topic", answerable=False, evidence=[]
    )
    assert validate.validate_schema([_row(), off]) == []


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (_row(split="train"), "split"),
        (_row(category="trivia"), "category"),
        (_row(question=""), "question"),
        (_row(question="x" * 1001), "question"),
        (_row(answerable="yes"), "answerable"),
        (_row(evidence=[]), "evidence"),  # answerable needs evidence
        (_row(answerable=False, evidence=["x"]), "evidence"),  # unanswerable has none
        (_row(evidence="not a list"), "evidence"),
        (_row(evidence=[""]), "evidence"),
        (_row(extra=1), "unknown"),
        ({k: v for k, v in _row().items() if k != "id"}, "id"),
        ("not a mapping", "mapping"),
    ],
    ids=repr,
)
def test_invalid_rows_are_reported(row: object, expected: str) -> None:
    errors = validate.validate_schema([row])
    assert errors and expected in errors[0]


def test_duplicate_ids_are_reported() -> None:
    errors = validate.validate_schema([_row(), _row()])
    assert any("duplicate id" in e for e in errors)


def test_summary_counts_per_category_and_split() -> None:
    rows = [
        _row(id="1"),
        _row(id="2", category="mixed"),
        _row(id="3", split="test"),
    ]
    summary = validate.summarize(rows)
    assert summary["category"] == {"code": 2, "mixed": 1}
    assert summary["split"] == {"dev": 2, "test": 1}
    assert summary["total"] == 3


# --- evidence matching -------------------------------------------------------------


def _chunk(content: str) -> validate.IngestedChunk:
    return validate.IngestedChunk(uuid.uuid4(), uuid.uuid4(), "slug", 0, content)


def test_evidence_must_match_exactly_one_chunk() -> None:
    chunks = [_chunk("alpha beta"), _chunk("beta gamma"), _chunk("delta")]
    ok = validate.check_evidence([_row(evidence=["alpha"])], chunks)
    none = validate.check_evidence([_row(evidence=["omega"])], chunks)
    many = validate.check_evidence([_row(evidence=["beta"])], chunks)
    assert ok == []
    assert "matches no chunk" in none[0]
    assert "matches 2 chunks" in many[0]


def test_relevant_chunk_ids() -> None:
    chunks = [_chunk("alpha beta"), _chunk("gamma"), _chunk("delta")]
    row = _row(evidence=["alpha", "delta"])
    assert validate.relevant_ids(row, chunks) == {
        chunks[0].chunk_id,
        chunks[2].chunk_id,
    }


# --- the real corpus ---------------------------------------------------------------

CODES = [
    "E-4012", "E-4013", "E-5001", "ERR_CONN_RESET", "ERR_SSL_PROTOCOL_ERROR",
    "HTTP 429", "HTTP 503", "ACME-AUTH-0042", "0x80070005", "SYNC_ERR_409",
    "AB-1234-XL", "v2.3.1",
]  # fmt: skip


def test_corpus_has_24_documents_of_120_to_300_words() -> None:
    docs = validate.load_corpus(EVAL_DIR / "corpus")
    assert len(docs) == 24
    assert len({d.slug for d in docs}) == 24
    for doc in docs:
        words = len(doc.content.split())
        assert 120 <= words <= 300, (doc.slug, words)


def test_corpus_covers_the_required_identifier_formats() -> None:
    everything = "\n".join(d.content for d in validate.load_corpus(EVAL_DIR / "corpus"))
    missing = [c for c in CODES if c not in everything]
    assert missing == []
    assert len(CODES) >= 10
    sso = next(
        d
        for d in validate.load_corpus(EVAL_DIR / "corpus")
        if d.slug == "sso-error-reference"
    )
    assert "E-4012" in sso.content and "E-4013" in sso.content  # the near pair


def test_corpus_index_lists_every_document() -> None:
    index = (EVAL_DIR / "corpus" / "INDEX.md").read_text()
    for doc in validate.load_corpus(EVAL_DIR / "corpus"):
        assert f"`{doc.slug}`" in index
        assert doc.title in index


def test_overlapping_documents_really_overlap() -> None:
    docs = {d.slug: d.content for d in validate.load_corpus(EVAL_DIR / "corpus")}
    a, b = docs["password-reset"], docs["account-recovery"]
    sentences = {s.strip() for s in re.split(r"(?<=[.])\s+", a) if len(s.split()) > 6}
    shared = [s for s in sentences if s in b]
    assert len(shared) >= 3


def test_shipped_questions_file_is_valid() -> None:
    rows = validate.load_questions(EVAL_DIR / "questions.yaml")
    assert validate.validate_schema(rows) == []


# --- end to end on a 3-document mini corpus (mechanics only) -----------------------

MINI = {
    "alpha": ("Alpha guide", "Zebra quasar procedure. Reset the zebra quasar widget by holding the button."),
    "beta": ("Beta guide", "Lantern orbit notes. The lantern orbit error is ERR_LANTERN_77 and is harmless."),
    "gamma": ("Gamma guide", "Nebula billing. Invoices for nebula accounts are issued on the first day."),
}  # fmt: skip


def _write_mini(directory: Path) -> Path:
    directory.mkdir()
    for slug, (title, body) in MINI.items():
        (directory / f"{slug}.md").write_text(f"# {title}\n\n{body}\n")
    return directory


async def _tenant_exists(tenant_id: uuid.UUID) -> bool:
    engine = create_async_engine(settings.migration_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return (
                await conn.execute(
                    text("SELECT count(*) FROM tenants WHERE id = :id"),
                    {"id": tenant_id},
                )
            ).scalar_one() == 1
    finally:
        await engine.dispose()


async def _indices_with_prefix(prefix: str) -> list[str]:
    found = await get_es().indices.get(
        index=f"{prefix}*", ignore_unavailable=True, allow_no_indices=True
    )
    return sorted(found)


async def test_mini_corpus_end_to_end_and_cleanup(tmp_path: Path) -> None:
    docs = validate.load_corpus(_write_mini(tmp_path / "corpus"))
    assert [d.slug for d in docs] == ["alpha", "beta", "gamma"]
    provider, es = FakeEmbeddingProvider(), get_es()
    before_prefix = settings.es_index_prefix
    questions = [
        _row(id="q1", evidence=["zebra quasar widget"], question="reset the zebra quasar widget"),
        _row(id="q2", evidence=["ERR_LANTERN_77"], category="code", question="ERR_LANTERN_77"),
        _row(id="q3", answerable=False, evidence=[], category="off_topic", question="weather tomorrow"),
    ]  # fmt: skip

    async with validate.eval_environment(es) as env:
        assert settings.es_index_prefix.startswith("eval-")
        assert settings.es_index_prefix != before_prefix
        chunks = await validate.ingest_corpus(env, docs, provider, es)
        tenant_id, prefix = env.tenant_id, settings.es_index_prefix
        assert {c.slug for c in chunks} == {"alpha", "beta", "gamma"}
        assert validate.check_evidence(questions, chunks) == []
        assert await _tenant_exists(tenant_id)
        assert await _indices_with_prefix(prefix)

        # Mechanics: the pipeline retrieves what the evidence says it should.
        for row in questions[:2]:
            relevant = validate.relevant_ids(row, chunks)
            result = await hybrid_search.hybrid_search(
                tenant_id, row["question"], 5, provider, es
            )
            ranked = [h.chunk_id for h in result.hits]
            assert metrics.hit_at_k(ranked, relevant, 3) == 1.0
            assert metrics.mrr_at_k(ranked, relevant, 5) == 1.0

    assert settings.es_index_prefix == before_prefix
    assert not await _tenant_exists(tenant_id)
    assert await _indices_with_prefix(prefix) == []


async def test_cleanup_runs_when_the_body_raises() -> None:
    es = get_es()
    before_prefix = settings.es_index_prefix
    seen: dict[str, object] = {}

    with pytest.raises(RuntimeError, match="boom"):
        async with validate.eval_environment(es) as env:
            seen["tenant"], seen["prefix"] = env.tenant_id, settings.es_index_prefix
            raise RuntimeError("boom")

    assert settings.es_index_prefix == before_prefix
    assert not await _tenant_exists(seen["tenant"])  # type: ignore[arg-type]
    assert await _indices_with_prefix(str(seen["prefix"])) == []
