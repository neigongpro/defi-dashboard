"""
Tests for database storage, snapshots, and rollups.
"""

import os
import tempfile
import pytest
from data.database import (
    init_db, insert_snapshots, get_latest_snapshots,
    get_pool_history, get_pool_by_id, execute_rollup_cleanup
)


@pytest.fixture
def test_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_defi.db")
    init_db(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


def test_insert_and_query_snapshots(test_db):
    sample_records = [
        {
            "ts": "2026-08-31T10:00:00Z",
            "pool_id": "test-pool-1",
            "project": "aave-v3",
            "chain": "Ethereum",
            "symbol": "USDC",
            "tvl_usd": 50000000.0,
            "apy": 5.5,
            "apy_base": 5.5,
            "apy_reward": 0.0,
            "apy_mean_30d": 5.2
        },
        {
            "ts": "2026-08-31T10:15:00Z",
            "pool_id": "test-pool-1",
            "project": "aave-v3",
            "chain": "Ethereum",
            "symbol": "USDC",
            "tvl_usd": 52000000.0,
            "apy": 5.7,
            "apy_base": 5.7,
            "apy_reward": 0.0,
            "apy_mean_30d": 5.3
        },
        {
            "ts": "2026-08-31T10:15:00Z",
            "pool_id": "test-pool-2",
            "project": "morpho-blue",
            "chain": "Base",
            "symbol": "USDT",
            "tvl_usd": 15000000.0,
            "apy": 8.5,
            "apy_base": 8.0,
            "apy_reward": 0.5,
            "apy_mean_30d": 8.1
        }
    ]

    inserted = insert_snapshots(sample_records, db_path=test_db)
    assert inserted == 3

    # Query latest
    latest = get_latest_snapshots(db_path=test_db, min_tvl=1000000)
    assert len(latest) == 2  # 2 unique pools

    # Check pool history
    history = get_pool_history("test-pool-1", days=7, db_path=test_db)
    assert len(history) == 2
    assert history[-1]["apy"] == 5.7


def test_rollup_cleanup(test_db):
    old_records = [
        {
            "ts": "2026-01-01T10:00:00Z",
            "pool_id": "old-pool",
            "project": "curve-dex",
            "chain": "Ethereum",
            "symbol": "3POOL",
            "tvl_usd": 20000000.0,
            "apy": 3.2,
            "apy_base": 3.0,
            "apy_reward": 0.2,
            "apy_mean_30d": 3.1
        }
    ]
    insert_snapshots(old_records, db_path=test_db)

    res = execute_rollup_cleanup(days_to_keep=30, db_path=test_db)
    assert res["rollups_created"] >= 1
    assert res["snapshots_purged"] >= 1
