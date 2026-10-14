"""Wilson interval and count formatting."""

import pytest

from eval import stats


def test_wilson_known_values() -> None:
    low, high = stats.wilson_interval(8, 10)
    assert low == pytest.approx(0.4902, abs=1e-3)
    assert high == pytest.approx(0.9433, abs=1e-3)


def test_wilson_edges_stay_inside_zero_one() -> None:
    assert stats.wilson_interval(0, 10)[0] == 0.0
    assert stats.wilson_interval(10, 10)[1] == 1.0
    _low, high = stats.wilson_interval(0, 10)
    assert 0.0 < high < 0.4
    assert stats.wilson_interval(0, 0) == (0.0, 1.0)


def test_wilson_is_narrower_with_more_data() -> None:
    small = stats.wilson_interval(8, 10)
    large = stats.wilson_interval(80, 100)
    assert (large[1] - large[0]) < (small[1] - small[0])


def test_wilson_rejects_impossible_counts() -> None:
    with pytest.raises(ValueError):
        stats.wilson_interval(11, 10)
    with pytest.raises(ValueError):
        stats.wilson_interval(-1, 10)


def test_count_and_percent_rounds_half_up() -> None:
    assert stats.count_pct(7, 8) == "7/8 = 88%"
    assert stats.count_pct(1, 3) == "1/3 = 33%"
    assert stats.count_pct(0, 0) == "0/0"
