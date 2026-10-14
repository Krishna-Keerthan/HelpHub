"""Report rendering on a toy result."""

from eval import report
from tests.helpers.eval_toys import CHUNKS, A, B, C, D, E, record


def _records() -> list:
    recs = [record(f"d{i}", vector=[A, B], keyword=[B, A], score=0.8) for i in range(2)]
    recs.append(
        record("worse", vector=[A], keyword=[B], hybrid=[B, C, D, E], score=0.7)
    )
    recs.append(
        record("u1", category="near_miss", answerable=False, vector=[C], score=0.65)
    )
    recs.append(record("t1", split="test", vector=[A], keyword=[A]))
    recs[-1].question = "What does E-4012 mean?"
    recs.append(
        record(
            "t2",
            split="test",
            category="off_topic",
            answerable=False,
            vector=[C],
            score=0.3,
        )
    )
    for r in recs:
        r.latency_ms = {"vector": 10.0, "keyword": 5.0, "hybrid": 12.0}
    return recs


def _render(**kw: object) -> tuple[str, dict]:
    args: dict = {
        "date": "2026-01-01", "env": {"git_sha": "abc"}, "records": _records(),
        "contents": CHUNKS, "n_docs": 2, "warmups": 3, "with_ablation": True,
        "checks": {"fusion": [], "relevance": ["z: bad"]},
    }  # fmt: skip
    args.update(kw)
    return report.render(**args)  # type: ignore[arg-type]


def test_report_has_every_section_with_counts_next_to_percentages() -> None:
    text, extra = _render()
    for heading in (
        "## Environment", "## Corpus and questions", "## Retrieval metrics",
        "## Latency", "## Integrity checks", "## Failure list",
        "## Gate analysis", "## Ablations", "## Limitations",
    ):  # fmt: skip
        assert heading in text
    assert "3/3 = 100%" in text or "2/3 = 67%" in text
    assert "Wilson" in text and "FAIL: z: bad" in text
    assert "only 4 unanswerable" in text
    assert "worse" in text  # failure list names the question
    assert "ablation_decision" in extra


def test_ablation_can_be_skipped() -> None:
    text, extra = _render(with_ablation=False)
    assert "## Ablations" not in text and extra["ablation_decision"] is None


def test_gate_recommendation_is_reported_on_both_splits() -> None:
    text, extra = _render()
    assert extra["gate_recommendation"]["rule"] in ("R1", "R2")
    assert "Test numbers are reported without re-tuning" in text
