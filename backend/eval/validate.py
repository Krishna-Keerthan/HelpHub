"""Evaluation corpus and question-set checks (pure: no database, no network).

Usage (from backend/):  uv run python -m eval.validate

Loads the corpus and questions.yaml and checks the schema. Evidence resolution
against ingested chunks (``check_evidence``) is used by the Session D runner.
"""

import sys
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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


# --- command line -----------------------------------------------------------------------


def main() -> int:
    docs = load_corpus(EVAL_DIR / "corpus")
    rows = load_questions(EVAL_DIR / "questions.yaml")
    errors = validate_schema(rows)
    print(f"documents: {len(docs)}")
    print(f"questions: {summarize(rows) if not errors else {'total': len(rows)}}")
    for error in errors:
        print(f"ERROR {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
