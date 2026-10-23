"""Interactive review of the 40 draft unanswerable questions.

Shows each question with the full text of the top-2 passages already recorded in
eval/unanswerable_review.md (parsed from that file; search is not re-run, no
scores) and records one answer per question in eval/unanswerable_decisions.json.
Resumable: the decisions file is rewritten after every answer.

Run from backend/:  uv run python scripts/review_unanswerable.py
"""

import json
import re
import sys
from pathlib import Path
from typing import TypedDict

EVAL = Path(__file__).resolve().parents[1] / "eval"
CANDIDATES = EVAL / "unanswerable_candidates.json"
REVIEW = EVAL / "unanswerable_review.md"
DECISIONS = EVAL / "unanswerable_decisions.json"

PROMPT = (
    "Does either passage state the answer to this question? "
    "[n] no  [y] yes  [u] unsure  [b] back  [q] quit: "
)

RULE = (
    "n = no passage states the answer, so the question STAYS in the unanswerable set. "
    "y = a passage states the answer, so the question is REMOVED. "
    "u = unsure, so the question is REMOVED (conservative). "
    "A passage that is only on the same topic is 'n'."
)

DECISION_FOR_ANSWER = {"n": "stays", "y": "removed", "u": "removed"}


class Passage(TypedDict):
    doc: str
    text: str


_HEADING = re.compile(r"^## (u-\d+): ")
_PASSAGE = re.compile(r"^Passage (\d+) \(`([^`]+)`\):\s*$")


def parse_review(text: str) -> dict[str, list[Passage]]:
    """Map question id -> its passages, in order, from unanswerable_review.md."""
    out: dict[str, list[Passage]] = {}
    qid: str | None = None
    current: Passage | None = None
    lines: list[str] = []

    def close() -> None:
        nonlocal current, lines
        if current is not None and qid is not None:
            current["text"] = "\n".join(lines).strip("\n")
            out[qid].append(current)
        current, lines = None, []

    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            close()
            qid = heading.group(1)
            out[qid] = []
            continue
        passage = _PASSAGE.match(line)
        if passage and qid is not None:
            close()
            current = {"doc": passage.group(2), "text": ""}
            continue
        if current is not None:
            if line.startswith(">"):
                lines.append(line[1:].removeprefix(" "))
            elif line.strip():
                close()
    close()
    return out


def load_candidates(path: Path = CANDIDATES) -> list[dict]:
    return json.loads(path.read_text())["questions"]


def decision_for(answer: str) -> str:
    return DECISION_FOR_ANSWER[answer]


def load_answers(path: Path = DECISIONS) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {d["id"]: d["answer"] for d in data["decisions"]}


def save_answers(
    answers: dict[str, str], candidates: list[dict], path: Path = DECISIONS
) -> None:
    """Write decisions in candidates-file order; split and category are copied, never computed."""
    rows = [
        {
            "id": q["id"],
            "answer": answers[q["id"]],
            "decision": decision_for(answers[q["id"]]),
            "split": q["split"],
            "category": q["category"],
        }
        for q in candidates
        if q["id"] in answers
    ]
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"rule": RULE, "decisions": rows}, indent=2) + "\n")
    tmp.replace(path)


def show(
    q: dict, passages: list[Passage], position: int, total: int, prior: str | None
) -> None:
    print(f"\n{'=' * 72}\n[{position}/{total}] {q['id']}  category: {q['category']}")
    print(f"\nQUESTION: {q['question']}")
    for i, p in enumerate(passages, 1):
        print(f"\n--- Passage {i} ({p['doc']}) ---\n{p['text']}")
    print(f"\nRULE: {RULE}")
    if prior:
        print(f"(current answer: {prior})")


def run(
    candidates: list[dict],
    passages: dict[str, list[Passage]],
    answers: dict[str, str],
    path: Path = DECISIONS,
    ask=input,
) -> bool:
    """Walk the questions. Returns True when every question is answered."""
    i = next(
        (k for k, q in enumerate(candidates) if q["id"] not in answers), len(candidates)
    )
    while i < len(candidates):
        q = candidates[i]
        show(q, passages[q["id"]], i + 1, len(candidates), answers.get(q["id"]))
        try:
            key = ask(PROMPT).strip().lower()
        except EOFError:
            return False
        if key == "q":
            return False
        if key == "b":
            i = max(i - 1, 0)
        elif key in DECISION_FOR_ANSWER:
            answers[q["id"]] = key
            save_answers(answers, candidates, path)
            i += 1
        else:
            print("Please type n, y, u, b or q.")
    return True


def main() -> int:
    candidates = load_candidates()
    passages = parse_review(REVIEW.read_text())
    problems = [q["id"] for q in candidates if len(passages.get(q["id"], [])) != 2]
    if problems:
        print(f"Cannot find two passages in {REVIEW.name} for: {', '.join(problems)}")
        return 1
    answers = load_answers()
    done = run(candidates, passages, answers)
    print(
        f"\n{len(answers)}/{len(candidates)} answered. "
        + ("All done." if done else "Run again to resume.")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
