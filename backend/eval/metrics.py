"""Retrieval metrics. Pure functions over ranked chunk-id lists; no I/O."""

import math
import uuid
from collections.abc import Collection, Sequence


def _top(ranked: Sequence[uuid.UUID], k: int) -> list[uuid.UUID]:
    if k < 1:
        raise ValueError("k must be positive")
    seen: set[uuid.UUID] = set()
    top: list[uuid.UUID] = []
    for item in ranked:
        if item not in seen:
            seen.add(item)
            top.append(item)
    return top[:k]


def hit_at_k(
    ranked: Sequence[uuid.UUID], relevant: Collection[uuid.UUID], k: int
) -> float:
    """1.0 if any relevant id is in the top k, else 0.0."""
    return 1.0 if any(item in relevant for item in _top(ranked, k)) else 0.0


def mrr_at_k(
    ranked: Sequence[uuid.UUID], relevant: Collection[uuid.UUID], k: int
) -> float:
    """Reciprocal rank of the first relevant id within the top k, else 0.0."""
    for rank, item in enumerate(_top(ranked, k), start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def recall_at_k(
    ranked: Sequence[uuid.UUID], relevant: Collection[uuid.UUID], k: int
) -> float:
    """Share of the relevant ids found in the top k."""
    if not relevant:
        raise ValueError("recall needs at least one relevant id")
    found = sum(1 for item in _top(ranked, k) if item in relevant)
    return found / len(set(relevant))


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def percentiles(values: Sequence[float], ps: Sequence[float]) -> dict[float, float]:
    """Linear-interpolation percentiles (like numpy's default) of ``values``."""
    if not values:
        raise ValueError("percentiles need at least one value")
    ordered = sorted(values)
    out: dict[float, float] = {}
    for p in ps:
        if not 0 <= p <= 100:
            raise ValueError("percentile must be between 0 and 100")
        position = (len(ordered) - 1) * p / 100
        low, high = math.floor(position), math.ceil(position)
        out[p] = ordered[low] + (ordered[high] - ordered[low]) * (position - low)
    return out
