"""Metric tables, failure lists, ablation and the integrity checks on toy data."""

import pytest

from eval import analysis, integrity
from eval.records import Ranking
from tests.helpers.eval_toys import A, B, C, D, E, F, record


def test_hit_counts_use_exact_rank_boundaries() -> None:
    recs = [
        record("r1", vector=[A, B, C, D, E]),  # rank 1
        record("r2", vector=[B, A, C, D, E]),  # rank 2
        record("r3", vector=[B, C, A, D, E]),  # rank 3
        record("r5", vector=[B, C, D, E, A]),  # rank 5
        record("r6", vector=[B, C, D, E, F, A]),  # rank 6: a miss at 5
    ]
    agg = analysis.aggregate(recs, "vector")
    assert (agg.n, agg.hit1, agg.hit3, agg.hit5) == (5, 1, 3, 4)
    assert agg.mrr == pytest.approx((1 + 1 / 2 + 1 / 3 + 1 / 5 + 1 / 6) / 5)


def test_aggregate_skips_unanswerable_and_filters_split_and_category() -> None:
    recs = [
        record("a", split="dev", category="code", vector=[A]),
        record("b", split="test", category="code", vector=[B]),
        record("c", split="dev", category="paraphrase", vector=[A]),
        record("u", split="dev", answerable=False, vector=[A]),
    ]
    assert analysis.aggregate(recs, "vector", split="dev").n == 2
    assert analysis.aggregate(recs, "vector", split="dev", category="code").n == 1
    assert analysis.aggregate(recs, "vector", split="test").hit5 == 0


def test_recall_at_5_is_the_fraction_of_distinct_relevant_chunks_found() -> None:
    rec = record("m", relevant={A, B}, vector=[A, C, D, E, F, B])
    assert analysis.aggregate([rec], "vector").recall5 == pytest.approx(0.5)


def test_failures_are_questions_where_hybrid_is_worse_than_the_best_branch() -> None:
    recs = [
        record("worse", vector=[A], keyword=[B], hybrid=[B, C, D, E, F]),
        record("same", vector=[A], keyword=[B], hybrid=[A]),
        record("better", vector=[B], keyword=[C], hybrid=[A]),
        record("miss_all", vector=[B], keyword=[C], hybrid=[B]),
    ]
    assert [r.id for r in analysis.failures(recs, "dev")] == ["worse"]
    assert [r.id for r in analysis.never_retrieved(recs, "dev")] == ["miss_all"]


def test_fuse_branches_truncates_then_fuses() -> None:
    rec = record(vector=[A, B, C], keyword=[C, B, A])
    rec.branches = {"vector": Ranking([A, B, C], []), "keyword": Ranking([C, B, A], [])}
    full = analysis.fuse(rec, rrf_k=60, candidates=50)
    assert full[0] in (A, C)
    assert analysis.fuse(rec, rrf_k=60, candidates=1) == [A, C]


def test_ablation_decision_requires_dev_gain_of_two_and_test_not_worse() -> None:
    dev = {(60, 50): 10, (30, 50): 12}
    test = {(60, 50): 7, (30, 50): 7}
    assert analysis.decide_ablation(dev, test, (60, 50)) == (30, 50)
    assert analysis.decide_ablation({**dev, (30, 50): 11}, test, (60, 50)) == (60, 50)
    assert analysis.decide_ablation(dev, {**test, (30, 50): 6}, (60, 50)) == (60, 50)


# --- integrity checks ----------------------------------------------------------------


def _good() -> list:
    rec = record("q", vector=[A, B], keyword=[B, C])
    rec.modes["hybrid"] = Ranking(analysis.fuse(rec, 60, 50), [])
    return [rec]


def test_fusion_check_passes_on_a_true_fusion_and_fires_when_corrupted() -> None:
    recs = _good()
    assert integrity.check_fusion(recs, 60) == []
    recs[0].modes["hybrid"] = Ranking(list(reversed(recs[0].modes["hybrid"].ids)), [])
    assert integrity.check_fusion(recs, 60) != []


def test_fusion_check_fires_with_the_wrong_rrf_k() -> None:
    # Two branches whose order flips between k=1 and k=60.
    rec = record("q", vector=[A, B, C, D], keyword=[C, B, D, A])
    rec.modes["hybrid"] = Ranking(analysis.fuse(rec, 1, 50), [])
    assert integrity.check_fusion([rec], 1) == []
    assert integrity.check_fusion([rec], 60) != []


def test_relevance_check_fires_on_an_answerable_question_without_relevant_chunks() -> (
    None
):
    assert integrity.check_relevance(_good()) == []
    bad = record("z", relevant=set())
    assert "z" in integrity.check_relevance([bad])[0]


def test_split_check_wants_24_dev_16_test_and_the_expected_categories() -> None:
    recs = [record(f"d{i}", split="dev") for i in range(24)]
    recs += [record(f"t{i}", split="test") for i in range(16)]
    expected = {"paraphrase": 40}
    assert integrity.check_splits(recs, expected) == []
    assert integrity.check_splits(recs[:-1], expected) != []
    assert integrity.check_splits(recs, {"paraphrase": 39, "code": 1}) != []


def test_evidence_check_flags_unresolved_snippets() -> None:
    assert integrity.check_evidence_resolves({"q1": 1, "q2": 2}) == []
    assert "q3" in integrity.check_evidence_resolves({"q3": 0})[0]
