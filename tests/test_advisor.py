"""
Tests for Rebalance Advisor and break-even calculations.
"""

import pytest
from data.database import insert_snapshots
from advisor.rebalance_advisor import evaluate_rebalance, estimate_transfer_gas


@pytest.fixture(autouse=True)
def seed_test_pools():
    sample_records = [
        {
            "ts": "2026-08-31T12:00:00Z",
            "pool_id": "seed-pool-aave",
            "project": "aave-v3",
            "chain": "Ethereum",
            "symbol": "USDT",
            "tvl_usd": 80000000.0,
            "apy": 4.5,
            "apy_base": 4.5,
            "apy_reward": 0.0,
            "apy_mean_30d": 4.4
        },
        {
            "ts": "2026-08-31T12:00:00Z",
            "pool_id": "seed-pool-morpho",
            "project": "morpho-blue",
            "chain": "Base",
            "symbol": "USDT",
            "tvl_usd": 25000000.0,
            "apy": 9.2,
            "apy_base": 9.0,
            "apy_reward": 0.2,
            "apy_mean_30d": 9.0
        }
    ]
    insert_snapshots(sample_records)


def test_gas_estimation():
    gas_same_chain = estimate_transfer_gas("base", "base")
    assert gas_same_chain < 0.50

    gas_cross_chain = estimate_transfer_gas("ethereum", "base")
    assert gas_cross_chain > 5.0


def test_evaluate_rebalance_hold_verdict():
    # If current APY is already very high (e.g. 50%), verdict should be HOLD
    res = evaluate_rebalance(
        asset="USDT",
        amount_usd=10000.0,
        current_protocol="aave-v3",
        current_chain="Ethereum",
        current_apy=50.0
    )
    assert res["verdict"] == "HOLD"
    assert "Оставить как есть" in res["verdict_summary"] or "Оставить на месте" in res["verdict_summary"]


def test_evaluate_rebalance_move_verdict():
    # If current APY is low (e.g. 1.0%), rebalance should find Morpho Base and recommend move
    res = evaluate_rebalance(
        asset="USDT",
        amount_usd=25000.0,
        current_protocol="aave-v3",
        current_chain="Ethereum",
        current_apy=1.0
    )
    assert res["verdict"] in ("STRONG_MOVE", "CONSIDER")
    assert res["best_alternative"] is not None
    assert res["best_alternative"]["apy_diff"] > 0
