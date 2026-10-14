"""Refusal-gate analysis: identifier-like tokens, rules R1/R2, sweep, dev-only choice.

Pure logic; no I/O. The production gate is implemented on Day 7; this module only
evaluates candidate rules on recorded retrieval results.

Rules (answer = the assistant would answer instead of refusing):
  R1  best vector cosine score >= T
  R2  R1, OR an identifier-like token of the query occurs (case-insensitively) in
      the content of one of the top-5 hybrid hits (a "code-literal match")
"""

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

# Identifier-like tokens. Ordered: earlier patterns win overlapping spans, so the
# SKU "AB-1234-XL" is not also reported as the error code "AB-1234".
#   SKU          AB-1234-XL        2-4 capitals, 3-5 digits, 1-3 capital/digit suffix
#   error code   E-4012, ERR-503   1-4 capitals, dash, 3-5 digits
#   SCREAMING    ERR_CONN_RESET    capitals/digits joined by at least one underscore
#   version      v2.3.1, v3.0      lower/upper v, then two or three dot-joined numbers
#   HTTP status  HTTP 429          "HTTP" then a 3-digit 1xx-5xx code
# Known false positives: standards such as "ISO-8601" look like error codes.
# Deliberately not matched: bare years, phone-like digit groups, plain acronyms.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sku", re.compile(r"\b[A-Z]{2,4}-\d{3,5}-[A-Z0-9]{1,3}\b")),
    ("error_code", re.compile(r"\b[A-Z]{1,4}-\d{3,5}\b")),
    ("screaming_snake", re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")),
    ("version", re.compile(r"\b[vV]\d+\.\d+(?:\.\d+)?\b")),
    ("http_status", re.compile(r"\bHTTP\s[1-5]\d{2}\b")),
)

THRESHOLDS: tuple[float, ...] = tuple(round(0.50 + 0.02 * i, 2) for i in range(11))
RULES = ("R1", "R2")


def identifier_tokens(text: str) -> list[str]:
    """Identifier-like tokens in order of appearance, without overlapping spans."""
    found: list[tuple[int, int, str]] = []
    for _, pattern in PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if all(end <= s or start >= e for s, e, _ in found):
                found.append((start, end, match.group()))
    return [token for _, _, token in sorted(found)]


def code_literal_match(query: str, contents: Sequence[str]) -> bool:
    haystack = [c.lower() for c in contents]
    return any(
        token.lower() in text for token in identifier_tokens(query) for text in haystack
    )


@dataclass(frozen=True)
class Item:
    """One question as the gate sees it."""

    qid: str
    category: str
    answerable: bool
    best_score: float  # best vector cosine score; -inf when nothing was retrieved
    query: str
    top5_contents: tuple[str, ...]  # contents of the top-5 hybrid hits


def answers(rule: str, threshold: float, item: Item) -> bool:
    if item.best_score >= threshold:
        return True
    if rule == "R1":
        return False
    if rule == "R2":
        return code_literal_match(item.query, item.top5_contents)
    raise ValueError(f"unknown rule {rule!r}")


@dataclass(frozen=True)
class GateResult:
    rule: str
    threshold: float
    n_answerable: int
    n_unanswerable: int
    false_refusals: int
    false_answers: int
    # category -> (false refusals, false answers)
    by_category: dict[str, tuple[int, int]] = field(default_factory=dict)
    refused_ids: tuple[str, ...] = ()
    wrongly_answered_ids: tuple[str, ...] = ()


def evaluate(items: Sequence[Item], rule: str, threshold: float) -> GateResult:
    refusals: dict[str, int] = defaultdict(int)
    wrong: dict[str, int] = defaultdict(int)
    refused_ids: list[str] = []
    wrong_ids: list[str] = []
    for item in items:
        answered = answers(rule, threshold, item)
        if item.answerable and not answered:
            refusals[item.category] += 1
            refused_ids.append(item.qid)
        elif not item.answerable and answered:
            wrong[item.category] += 1
            wrong_ids.append(item.qid)
    categories = sorted({i.category for i in items})
    return GateResult(
        rule,
        threshold,
        sum(1 for i in items if i.answerable),
        sum(1 for i in items if not i.answerable),
        sum(refusals.values()),
        sum(wrong.values()),
        {c: (refusals[c], wrong[c]) for c in categories},
        tuple(refused_ids),
        tuple(wrong_ids),
    )


def sweep(
    items: Sequence[Item],
    rules: Sequence[str] = RULES,
    thresholds: Sequence[float] = THRESHOLDS,
) -> list[GateResult]:
    return [evaluate(items, rule, t) for rule in rules for t in thresholds]


@dataclass(frozen=True)
class Choice:
    rule: str
    threshold: float
    low: float  # plateau bounds (inclusive)
    high: float
    plateau_steps: int


def choose(results: Sequence[GateResult], max_false_answers: int = 1) -> Choice | None:
    """Pick (rule, T) from DEV results only.

    Minimise false refusals subject to false_answers <= max_false_answers. The
    optimum is usually a plateau of consecutive thresholds: take the middle step
    (the upper middle when the count is even). With several plateaus, the longest
    wins; equal lengths prefer R1 (simpler), then the larger T.
    """
    feasible = [r for r in results if r.false_answers <= max_false_answers]
    if not feasible:
        return None
    best = min(r.false_refusals for r in feasible)
    grid = sorted({r.threshold for r in results})
    position = {t: i for i, t in enumerate(grid)}
    runs: list[tuple[str, list[float]]] = []
    for rule in sorted({r.rule for r in feasible}):
        ts = sorted(
            r.threshold for r in feasible if r.rule == rule and r.false_refusals == best
        )
        run: list[float] = []
        for t in ts:
            if run and position[t] != position[run[-1]] + 1:
                runs.append((rule, run))
                run = []
            run.append(t)
        if run:
            runs.append((rule, run))
    rule, run = max(runs, key=lambda rr: (len(rr[1]), rr[0] == "R1", rr[1][-1]))
    return Choice(rule, run[len(run) // 2], run[0], run[-1], len(run))
