"""Pure statistical helpers."""

import pytest

from app.services.statistics import (
    ewma,
    linear_trend,
    mad,
    mean,
    median,
    pct_change,
    percentile,
    robust_zscore,
    safe_div,
    split_halves,
    stdev,
    zscore,
)


def test_percentile_matches_known_values():
    values = list(range(1, 101))
    assert percentile(values, 50) == pytest.approx(50.5)
    assert percentile(values, 95) == pytest.approx(95.05, abs=0.1)
    assert percentile(values, 0) == 1
    assert percentile(values, 100) == 100


def test_percentile_handles_empty_and_single():
    assert percentile([], 50) is None
    assert percentile([7.0], 99) == 7.0


def test_percentile_clamps_out_of_range_q():
    assert percentile([1, 2, 3], 150) == 3
    assert percentile([1, 2, 3], -10) == 1


def test_mean_and_stdev():
    assert mean([2, 4, 6]) == 4
    assert stdev([2, 4, 6]) == pytest.approx(2.0)
    assert stdev([5]) is None
    assert mean([]) is None


def test_median_and_mad():
    assert median([1, 3, 5, 7]) == 4
    assert mad([1, 3, 5, 7]) == pytest.approx(2.0)


def test_zscore_and_robust_zscore():
    baseline = [10.0] * 10 + [11.0] * 10
    assert abs(zscore(10.5, baseline)) < 1.5
    assert zscore(100, baseline) > 3
    assert robust_zscore(100, baseline) > 3


def test_robust_zscore_is_not_masked_by_outliers():
    """Contaminating outliers inflate stdev, hiding a genuine deviation.

    The median/MAD estimator keeps its scale, so the same point still reads as
    anomalous.
    """
    baseline = [10.0, 10.4, 9.6, 10.2, 9.8, 10.1, 9.9, 10.3, 9.7, 10.0] * 2
    contaminated = [*baseline, 900.0, 950.0]
    classic = zscore(13.0, contaminated)
    robust = robust_zscore(13.0, contaminated)
    assert abs(classic) < 1.0, "stdev is inflated by the outliers, masking the deviation"
    assert abs(robust) > 3.0, "MAD-based score still flags the deviation"


def test_robust_zscore_handles_a_pinned_signal():
    """A metric pinned at a constant has zero MAD. A later jump must still be
    detectable rather than returning an undefined score."""
    pinned = [42.0] * 18 + [42.5, 41.5]
    assert robust_zscore(120.0, pinned) is not None
    assert robust_zscore(42.0, [42.0] * 20) is None  # genuinely no dispersion


def test_zscore_returns_none_for_zero_variance():
    assert zscore(5, [5, 5, 5, 5]) is None


def test_ewma_smooths_towards_recent_values():
    smoothed = ewma([0, 0, 0, 10, 10, 10], alpha=0.5)
    assert smoothed[-1] > smoothed[0]
    assert smoothed[-1] < 10


def test_linear_trend_sign():
    assert linear_trend([1, 2, 3, 4, 5]) == pytest.approx(1.0)
    assert linear_trend([5, 4, 3, 2, 1]) == pytest.approx(-1.0)
    assert linear_trend([1, 2]) is None


def test_pct_change():
    assert pct_change(100, 130) == pytest.approx(30.0)
    assert pct_change(100, 70) == pytest.approx(-30.0)
    assert pct_change(0, 10) is None
    assert pct_change(None, 10) is None


def test_split_halves():
    first, second = split_halves([1, 2, 3, 4, 5, 6])
    assert first == [1, 2, 3]
    assert second == [4, 5, 6]
    assert split_halves([1, 2]) == ([], [])


def test_safe_div():
    assert safe_div(10, 4) == 2.5
    assert safe_div(10, 0) is None
    assert safe_div(None, 4) is None
