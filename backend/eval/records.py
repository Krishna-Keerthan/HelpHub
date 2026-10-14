"""Plain data recorded by the evaluation run. JSON-serialisable via ``to_json``."""

import uuid
from dataclasses import dataclass, field
from typing import Any

MODES = ("vector", "keyword", "hybrid")


@dataclass(frozen=True)
class Ranking:
    ids: list[uuid.UUID]
    scores: list[float]


@dataclass
class Record:
    id: str
    split: str
    category: str
    answerable: bool
    question: str
    relevant: set[uuid.UUID]
    modes: dict[str, Ranking]  # top 10 per mode
    branches: dict[str, Ranking]  # up to 50 candidates per hybrid branch
    fallback: bool = False  # the vector exact fallback fired
    latency_ms: dict[str, float] = field(default_factory=dict)


def to_json(record: Record) -> dict[str, Any]:
    def ranking(r: Ranking) -> dict[str, Any]:
        return {"ids": [str(i) for i in r.ids], "scores": r.scores}

    return {
        "id": record.id,
        "split": record.split,
        "category": record.category,
        "answerable": record.answerable,
        "question": record.question,
        "relevant": sorted(str(i) for i in record.relevant),
        "modes": {m: ranking(r) for m, r in record.modes.items()},
        "branches": {m: ranking(r) for m, r in record.branches.items()},
        "fallback": record.fallback,
        "latency_ms": record.latency_ms,
    }
