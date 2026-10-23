"""Evaluation plumbing: metrics, schema checks and corpus sanity."""

import re
import uuid
from pathlib import Path

import pytest

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
