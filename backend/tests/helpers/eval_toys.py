"""Toy records shared by the evaluation logic tests (no database)."""

import uuid

from eval.records import Ranking, Record

A, B, C, D, E, F = (uuid.UUID(int=i) for i in range(1, 7))
CHUNKS = {
    A: "alpha text",
    B: "beta E-4012 text",
    C: "gamma text",
    D: "delta",
    E: "e",
    F: "f",
}


def ranking(*ids: uuid.UUID, score: float = 0.9) -> Ranking:
    return Ranking(list(ids), [round(score - 0.01 * i, 4) for i in range(len(ids))])


def record(
    qid: str = "q1",
    *,
    split: str = "dev",
    category: str = "paraphrase",
    answerable: bool = True,
    relevant: set[uuid.UUID] | None = None,
    vector: list[uuid.UUID] | None = None,
    keyword: list[uuid.UUID] | None = None,
    hybrid: list[uuid.UUID] | None = None,
    score: float = 0.9,
) -> Record:
    v, k = vector or [], keyword or []
    return Record(
        id=qid,
        split=split,
        category=category,
        answerable=answerable,
        question=f"question {qid}",
        relevant=relevant if relevant is not None else ({A} if answerable else set()),
        modes={
            "vector": ranking(*v, score=score),
            "keyword": ranking(*k),
            "hybrid": ranking(*(hybrid if hybrid is not None else v)),
        },
        branches={"vector": ranking(*v, score=score), "keyword": ranking(*k)},
    )
