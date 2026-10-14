"""Integrity checks for an evaluation run. Each returns a list of problems."""

from collections import Counter
from collections.abc import Mapping, Sequence

from eval import analysis
from eval.records import Record

EXPECTED_SPLITS = {"dev": 24, "test": 16}


def check_fusion(records: Sequence[Record], rrf_k: int) -> list[str]:
    """Re-fusing the recorded branch lists must reproduce the hybrid ranking."""
    problems = []
    for r in records:
        recorded = r.modes["hybrid"].ids
        refused = analysis.fuse(
            r,
            rrf_k,
            candidates=len(r.branches["vector"].ids) + len(r.branches["keyword"].ids),
        )
        if refused[: len(recorded)] != recorded:
            problems.append(f"{r.id}: hybrid ranking differs from fuse_rrf(k={rrf_k})")
    return problems


def check_evidence_resolves(matches: Mapping[str, int]) -> list[str]:
    """``matches``: question id -> smallest number of chunks any evidence snippet hit."""
    return [
        f"{q}: an evidence snippet resolves to no chunk"
        for q, n in matches.items()
        if n < 1
    ]


def check_relevance(records: Sequence[Record]) -> list[str]:
    return [
        f"{r.id}: answerable question has no relevant chunk"
        for r in records
        if r.answerable and not r.relevant
    ]


def check_splits(records: Sequence[Record], categories: Mapping[str, int]) -> list[str]:
    problems = []
    splits = Counter(r.split for r in records)
    if dict(splits) != EXPECTED_SPLITS:
        problems.append(f"split sizes {dict(splits)} != {EXPECTED_SPLITS}")
    found = dict(Counter(r.category for r in records))
    if found != dict(categories):
        problems.append(f"categories {found} != {dict(categories)}")
    return problems
