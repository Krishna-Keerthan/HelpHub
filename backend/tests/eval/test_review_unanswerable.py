"""scripts/review_unanswerable.py: parsing, resumption, answer mapping, splits copied from candidates."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "review_unanswerable.py"


def load():
    spec = importlib.util.spec_from_file_location("review_unanswerable", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = load()

REVIEW = """# Review

## u-001: First?

Category: `near_miss`. Split: `dev`.

Passage 1 (`doc-a`):

> Line one.
>
> Line two with | pipe.

Passage 2 (`doc-b`):

> Other text.

Decision: [2] keep  [1] remove (a passage answers it)

## u-002: Second?

Passage 1 (`doc-c`):

> C text.

Passage 2 (`doc-d`):

> D text.

Decision: [1] keep  [2] remove
"""

# Deliberately not the alternating dev/test pattern: the script must copy, not recompute.
CANDIDATES = [
    {"id": "u-001", "question": "First?", "category": "near_miss", "split": "test"},
    {"id": "u-002", "question": "Second?", "category": "off_topic", "split": "test"},
]


def scripted(keys: list[str]):
    it = iter(keys)
    return lambda _prompt: next(it)


def test_parse_review_extracts_full_passages_in_order() -> None:
    parsed = mod.parse_review(REVIEW)
    assert list(parsed) == ["u-001", "u-002"]
    assert parsed["u-001"][0] == {
        "doc": "doc-a",
        "text": "Line one.\n\nLine two with | pipe.",
    }
    assert parsed["u-001"][1] == {"doc": "doc-b", "text": "Other text."}
    assert parsed["u-002"][1]["text"] == "D text."


def test_parse_real_review_file_has_two_passages_per_candidate() -> None:
    candidates = mod.load_candidates()
    parsed = mod.parse_review(mod.REVIEW.read_text())
    assert len(candidates) == 40
    for q in candidates:
        assert len(parsed[q["id"]]) == 2
        assert all(p["text"] for p in parsed[q["id"]])


@pytest.mark.parametrize(
    ("answer", "decision"), [("n", "stays"), ("y", "removed"), ("u", "removed")]
)
def test_answer_maps_to_decision(answer: str, decision: str) -> None:
    assert mod.decision_for(answer) == decision


def test_prompt_avoids_keep_remove_words() -> None:
    assert "keep" not in mod.PROMPT.lower()
    assert "remove" not in mod.PROMPT.lower()


def test_saved_file_copies_split_and_category_and_has_no_passage_text(
    tmp_path: Path,
) -> None:
    path = tmp_path / "decisions.json"
    parsed = mod.parse_review(REVIEW)
    answers: dict[str, str] = {}
    assert mod.run(CANDIDATES, parsed, answers, path, scripted(["n", "y"]))
    data = json.loads(path.read_text())
    assert data["rule"] == mod.RULE
    assert data["decisions"] == [
        {
            "id": "u-001",
            "answer": "n",
            "decision": "stays",
            "split": "test",
            "category": "near_miss",
        },
        {
            "id": "u-002",
            "answer": "y",
            "decision": "removed",
            "split": "test",
            "category": "off_topic",
        },
    ]
    assert "Line one" not in path.read_text()


def test_written_after_every_answer_and_resumes(tmp_path: Path) -> None:
    path = tmp_path / "decisions.json"
    parsed = mod.parse_review(REVIEW)
    answers: dict[str, str] = {}
    assert not mod.run(CANDIDATES, parsed, answers, path, scripted(["u", "q"]))
    assert mod.load_answers(path) == {"u-001": "u"}

    resumed = mod.load_answers(path)
    shown: list[str] = []

    def ask(prompt: str) -> str:
        shown.append(prompt)
        return "n"

    assert mod.run(CANDIDATES, parsed, resumed, path, ask)
    assert len(shown) == 1  # only u-002 was asked
    assert mod.load_answers(path) == {"u-001": "u", "u-002": "n"}


def test_back_allows_changing_an_answer_and_bad_keys_reask(tmp_path: Path) -> None:
    path = tmp_path / "decisions.json"
    parsed = mod.parse_review(REVIEW)
    answers: dict[str, str] = {}
    keys = ["y", "x", "b", "n", "n"]
    assert mod.run(CANDIDATES, parsed, answers, path, scripted(keys))
    assert mod.load_answers(path) == {"u-001": "n", "u-002": "n"}
