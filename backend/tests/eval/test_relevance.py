"""Relevance is resolved from chunk CONTENT with case-sensitive exact substrings."""

import uuid

from eval.validate import IngestedChunk, relevant_ids

DOC = uuid.UUID(int=99)


def _chunk(n: int, slug: str, content: str) -> IngestedChunk:
    return IngestedChunk(uuid.UUID(int=n), DOC, slug, 0, content)


CHUNKS = [
    _chunk(1, "sso-setup", "Assertion signature invalid means the cert expired."),
    _chunk(2, "billing", "Data is kept for 90 days after the downgrade."),
    _chunk(3, "assertion-signature-invalid", "Unrelated body text."),
]


def test_a_chunk_is_relevant_when_its_content_has_any_evidence_snippet() -> None:
    row = {"evidence": ["kept for 90 days", "no such text"]}
    assert relevant_ids(row, CHUNKS) == {uuid.UUID(int=2)}


def test_matching_is_by_content_not_by_title_or_slug() -> None:
    row = {"evidence": ["assertion-signature-invalid"]}
    assert relevant_ids(row, CHUNKS) == set()


def test_matching_is_case_sensitive() -> None:
    assert relevant_ids({"evidence": ["assertion signature invalid"]}, CHUNKS) == set()
    assert relevant_ids({"evidence": ["Assertion signature invalid"]}, CHUNKS) == {
        uuid.UUID(int=1)
    }


def test_unanswerable_question_has_no_relevant_chunks() -> None:
    assert relevant_ids({"evidence": []}, CHUNKS) == set()
