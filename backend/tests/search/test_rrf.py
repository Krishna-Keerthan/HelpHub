import uuid

import pytest

from app.services.rrf import fuse_rrf

A, B, C, D = (uuid.UUID(int=i) for i in range(1, 5))


def test_empty_inputs() -> None:
    assert fuse_rrf([]) == []
    assert fuse_rrf([[], []]) == []


def test_single_list_keeps_order_with_exact_scores() -> None:
    assert fuse_rrf([[A, B]], k=60) == [(A, 1 / 61), (B, 1 / 62)]


def test_item_in_both_lists_outranks_single_source() -> None:
    fused = fuse_rrf([[A, B], [C, B]], k=60)
    assert fused[0][0] == B
    assert fused[0][1] == pytest.approx(1 / 62 + 1 / 62)
    assert {i for i, _ in fused} == {A, B, C}


def test_higher_rank_scores_higher() -> None:
    fused = dict(fuse_rrf([[A, B, C]]))
    assert fused[A] > fused[B] > fused[C]


def test_ties_keep_first_appearance_order() -> None:
    assert [i for i, _ in fuse_rrf([[A], [B]])] == [A, B]
    assert [i for i, _ in fuse_rrf([[B], [A]])] == [B, A]


def test_duplicate_within_a_list_counts_once_at_best_rank() -> None:
    assert dict(fuse_rrf([[A, A, B]], k=60)) == {A: 1 / 61, B: 1 / 63}


def test_k_changes_the_scores() -> None:
    assert fuse_rrf([[A]], k=1)[0][1] == pytest.approx(1 / 2)
    assert fuse_rrf([[A]], k=60)[0][1] == pytest.approx(1 / 61)


@pytest.mark.parametrize("k", [0, -1])
def test_non_positive_k_is_rejected(k: int) -> None:
    with pytest.raises(ValueError):
        fuse_rrf([[A]], k=k)


def test_does_not_mutate_inputs() -> None:
    lists = [[A, B], [B, D]]
    fuse_rrf(lists)
    assert lists == [[A, B], [B, D]]
