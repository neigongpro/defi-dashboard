"""
Tests for metrics calculations and scoring algorithms.
"""

from data.metrics_engine import compute_stability_score, get_enriched_pools, get_market_overview


def test_stability_score_calculation():
    # Stable series
    stable_series = [5.0, 5.1, 4.9, 5.0, 5.2, 5.0, 5.1]
    score_stable = compute_stability_score(stable_series)
    assert score_stable >= 0.85

    # Volatile series
    volatile_series = [2.0, 45.0, 1.5, 30.0, 2.1, 50.0]
    score_volatile = compute_stability_score(volatile_series)
    assert score_volatile < 0.65


def test_market_overview_structure():
    overview = get_market_overview()
    assert "total_tvl_monitored" in overview
    assert "total_pools_count" in overview
    assert "avg_stable_apy" in overview
    assert "avg_eth_apy" in overview
    assert overview["total_pools_count"] >= 0
