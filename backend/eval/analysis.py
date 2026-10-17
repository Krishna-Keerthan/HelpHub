"""Metric tables, failure lists, gate inputs and ablations over recorded results.

Pure functions over ``Record`` lists; nothing here touches a database or ES.
Metrics cover ANSWERABLE questions only.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from eval import metrics
from eval.gate_rules import Item
from eval.records import MODES, Record

TOP_K = 5

RRF_K = 60


def _fuse_rrf(
    ranked_lists: Sequence[Sequence[uuid.UUID]], k: int
) -> list[tuple[uuid.UUID, float]]:
    """Reciprocal rank fusion over best-first id lists; ties keep first appearance."""
    scores: dict[uuid.UUID, float] = {}
    for ranked in ranked_lists:
        seen: set[uuid.UUID] = set()
        for rank, item in enumerate(ranked, start=1):
            if item in seen:
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: -pair[1])


@dataclass(frozen=True)
class Agg:
    n: int
    hit1: int
    hit3: int
    hit5: int
    mrr: float  # mean reciprocal rank at 10
    recall5: float  # mean over questions of (distinct relevant chunks in top 5) / (relevant chunks)


def _answerable(
    records: Sequence[Record], split: str | None, category: str | None
) -> list[Record]:
    return [
        r
        for r in records
        if r.answerable
        and (split is None or r.split == split)
        and (category is None or r.category == category)
    ]


def aggregate(
    records: Sequence[Record],
    mode: str,
    *,
    split: str | None = None,
    category: str | None = None,
) -> Agg:
    rows = _answerable(records, split, category)
    ranked = [(r.modes[mode].ids, r.relevant) for r in rows]
    return Agg(
        n=len(rows),
        hit1=sum(int(metrics.hit_at_k(i, rel, 1)) for i, rel in ranked),
        hit3=sum(int(metrics.hit_at_k(i, rel, 3)) for i, rel in ranked),
        hit5=sum(int(metrics.hit_at_k(i, rel, 5)) for i, rel in ranked),
        mrr=metrics.mean([metrics.mrr_at_k(i, rel, 10) for i, rel in ranked]),
        recall5=metrics.mean([metrics.recall_at_k(i, rel, 5) for i, rel in ranked]),
    )


def _hit5(record: Record, mode: str) -> bool:
    return bool(metrics.hit_at_k(record.modes[mode].ids, record.relevant, TOP_K))


def failures(records: Sequence[Record], split: str) -> list[Record]:
    """Answerable questions where hybrid hit@5 is worse than the better single mode."""
    return [
        r
        for r in _answerable(records, split, None)
        if not _hit5(r, "hybrid") and (_hit5(r, "vector") or _hit5(r, "keyword"))
    ]


def never_retrieved(records: Sequence[Record], split: str) -> list[Record]:
    """Answerable questions that no mode retrieved in the top 5."""
    return [
        r
        for r in _answerable(records, split, None)
        if not any(_hit5(r, m) for m in MODES)
    ]


def fuse(record: Record, rrf_k: int, candidates: int) -> list[uuid.UUID]:
    """Fuse the recorded branch lists, each truncated to ``candidates`` ids."""
    lists = [
        record.branches["vector"].ids[:candidates],
        record.branches["keyword"].ids[:candidates],
    ]
    return [chunk_id for chunk_id, _ in _fuse_rrf(lists, k=rrf_k)]


def ablation_hits(
    records: Sequence[Record], split: str, rrf_k: int, candidates: int
) -> int:
    return sum(
        int(metrics.hit_at_k(fuse(r, rrf_k, candidates), r.relevant, TOP_K))
        for r in _answerable(records, split, None)
    )


Setting = tuple[int, int]  # (rrf_k, candidates)


def decide_ablation(
    dev: Mapping[Setting, int], test: Mapping[Setting, int], default: Setting
) -> Setting:
    """Change the default only if dev gains >= 2 questions AND test is not worse."""
    eligible = [
        s
        for s in dev
        if s != default and dev[s] - dev[default] >= 2 and test[s] >= test[default]
    ]
    if not eligible:
        return default
    return max(eligible, key=lambda s: (dev[s], test[s]))


def gate_items(
    records: Sequence[Record], contents: Mapping[uuid.UUID, str], split: str
) -> list[Item]:
    items: list[Item] = []
    for r in records:
        if r.split != split:
            continue
        scores = r.modes["vector"].scores
        top5 = tuple(contents[i] for i in r.modes["hybrid"].ids[:TOP_K])
        items.append(
            Item(
                r.id,
                r.category,
                r.answerable,
                scores[0] if scores else float("-inf"),
                r.question,
                top5,
            )
        )
    return items


def latency_table(records: Sequence[Record]) -> dict[str, tuple[int, float, float]]:
    out: dict[str, tuple[int, float, float]] = {}
    for mode in MODES:
        values = [r.latency_ms[mode] for r in records if mode in r.latency_ms]
        if values:
            p = metrics.percentiles(values, [50, 95])
            out[mode] = (len(values), p[50], p[95])
    return out
