"""Reciprocal rank fusion over ranked id lists.

Only ranks enter the fusion; scores from different retrievers are never
compared (AR-11).
"""

import uuid
from collections.abc import Sequence

DEFAULT_RRF_K = 60


def fuse_rrf(
    ranked_lists: Sequence[Sequence[uuid.UUID]], k: int = DEFAULT_RRF_K
) -> list[tuple[uuid.UUID, float]]:
    """Fuse best-first id lists; returns (id, score) best first.

    score(id) = sum over lists of 1 / (k + rank), rank starting at 1. An id
    repeated inside one list counts once, at its best rank. Ties keep the order
    of first appearance (list order, then position).
    """
    if k <= 0:
        raise ValueError("k must be positive")
    scores: dict[uuid.UUID, float] = {}
    for ranked in ranked_lists:
        seen: set[uuid.UUID] = set()
        for rank, item in enumerate(ranked, start=1):
            if item in seen:
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: -pair[1])  # sort is stable
