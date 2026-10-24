"""Retrieval-gate rules R0/R1: sweep, selection and the TEST lock (docs/eval/protocol.md).

Pure logic; no database, no network. A question is answered if at least one of
its top-5 hybrid hits satisfies the rule on that same hit (protocol section 2).
"""

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

T_GRID: tuple[float, ...] = tuple(round(0.50 + 0.01 * i, 2) for i in range(31))
S_GRID: tuple[float, ...] = tuple(round(0.05 * i, 2) for i in range(11))


@dataclass(frozen=True)
class HitFeatures:
    cosine: float
    text_score: float | None  # None (not in the keyword branch) counts as 0


@dataclass(frozen=True)
class QuestionFeatures:
    qid: str
    split: str
    answerable: bool
    hits: tuple[HitFeatures, ...]  # top-5 hybrid hits


@dataclass(frozen=True)
class Rule:
    name: str  # "R0" or "R1"
    t: float
    s: float = 0.0


@dataclass(frozen=True)
class Scored:
    rule: Rule
    wrongly_refused: int  # answerable questions refused
    n_answerable: int
    wrongly_answered: int  # unanswerable questions answered
    n_unanswerable: int

    @property
    def a(self) -> Fraction:
        return Fraction(self.wrongly_refused, self.n_answerable)

    @property
    def u(self) -> Fraction:
        return Fraction(self.wrongly_answered, self.n_unanswerable)

    @property
    def worst(self) -> Fraction:
        return max(self.a, self.u)


def answers(rule: Rule, hits: Sequence[HitFeatures]) -> bool:
    s = rule.s if rule.name == "R1" else 0.0
    return any(h.cosine >= rule.t and (h.text_score or 0.0) >= s for h in hits)


def score(rule: Rule, items: Sequence[QuestionFeatures]) -> Scored:
    refused = answered = n_a = n_u = 0
    for item in items:
        answered_it = answers(rule, item.hits)
        if item.answerable:
            n_a += 1
            refused += not answered_it
        else:
            n_u += 1
            answered += answered_it
    return Scored(rule, refused, n_a, answered, n_u)


def sweep(items: Sequence[QuestionFeatures]) -> tuple[list[Scored], list[Scored]]:
    """(R0 over the t grid, R1 over the t x s grid; s = 0.00 is R0 and is left out)."""
    r0 = [score(Rule("R0", t), items) for t in T_GRID]
    r1 = [score(Rule("R1", t, s), items) for t in T_GRID for s in S_GRID if s > 0]
    return r0, r1


def choose(r0: Sequence[Scored], r1: Sequence[Scored]) -> Scored:
    """Minimise max(A, U); ties to the higher t, then (R1) the higher s.

    R1 is chosen only if strictly better than the best R0.
    """
    best0 = min(r0, key=lambda x: (x.worst, -x.rule.t))
    if not r1:
        return best0
    best1 = min(r1, key=lambda x: (x.worst, -x.rule.t, -x.rule.s))
    return best1 if best1.worst < best0.worst else best0


def to_json(x: Scored) -> dict[str, Any]:
    return {
        "rule": x.rule.name,
        "t": x.rule.t,
        "s": x.rule.s,
        "wrongly_refused": x.wrongly_refused,
        "n_answerable": x.n_answerable,
        "wrongly_answered": x.wrongly_answered,
        "n_unanswerable": x.n_unanswerable,
    }


def features_to_json(items: Sequence[QuestionFeatures]) -> list[dict[str, Any]]:
    return [
        {
            "id": i.qid,
            "split": i.split,
            "answerable": i.answerable,
            "hits": [{"cosine": h.cosine, "text_score": h.text_score} for h in i.hits],
        }
        for i in items
    ]


class TestAlreadyRun(RuntimeError):
    """docs/eval/test_result.json exists: TEST was already evaluated."""

    __test__ = False  # not a pytest class


def refuse_if_test_done(result_path: Path) -> None:
    if result_path.exists():
        raise TestAlreadyRun(
            f"{result_path.name} exists; delete it and add a written amendment to re-run"
        )


def write_test_result(result_path: Path, payload: dict[str, Any]) -> None:
    """Exclusive create: a second writer fails instead of overwriting the lock."""
    fd = os.open(result_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def rule_from_json(d: dict[str, Any]) -> Rule:
    return Rule(d["rule"], float(d["t"]), float(d["s"]))
