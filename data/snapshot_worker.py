"""
Snapshot Worker — Background ingestion engine.
Fetches live on-chain pool yields from DefiLlama Yields API every 15 minutes,
filters for Tier-1 protocols, and saves snapshots to SQLite.
Also provides bootstrap backfilling of 30-day historical chart data for top pools.
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import init_db, insert_snapshots, get_connection

# Top 10 Tier-1 Protocol slug prefixes and aliases
TIER1_PROTOCOLS = {
    # 1. Aave
    "aave-v3", "aave-v2", "aave",
    # 2. Morpho
    "morpho-blue", "morpho", "morpho-aave",
    # 3. Compound
    "compound-v3", "compound-v2", "compound",
    # 4. Spark
    "spark", "spark-lending", "spark-savings",
    # 5. Fluid
    "fluid", "fluid-lending",
    # 6. Lido
    "lido",
    # 7. Uniswap
    "uniswap-v3", "uniswap-v2", "uniswap",
    # 8. Curve
    "curve-dex", "curve-finance", "curve",
    # 9. Pendle
    "pendle",
    # 10. Aerodrome
    "aerodrome", "aerodrome-v2"
}

ALLOWED_CHAINS = {
    "ethereum", "arbitrum", "base", "optimism", "polygon", "bsc", "avalanche", "gnosis", "solana"
}


def is_tier1_protocol(project_slug: str) -> bool:
    """Check if the project matches our Tier-1 protocol definition."""
    p = project_slug.lower().strip()
    return any(p == t or p.startswith(t) for t in TIER1_PROTOCOLS)


def fetch_and_store_snapshots(
    min_tvl: float = 1_000_000,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch all current pools, filter for Tier-1 protocols, and store in SQLite.
    Returns the list of processed snapshot records.
    """
    init_db(db_path)
    url = "https://yields.llama.fi/pools"

    print(f"[{datetime.now(timezone.utc).isoformat()}] [Worker] Fetching live yields from {url}...")
    try:
        resp = requests.get(url, timeout=35)
        resp.raise_for_status()
        raw_data = resp.json().get("data", [])
    except Exception as e:
        print(f"[Worker] Fetch error: {e}")
        return []

    records: List[Dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for item in raw_data:
        project = (item.get("project") or "").lower()
        chain = (item.get("chain") or "").lower()
        tvl = item.get("tvlUsd") or 0.0
        apy = item.get("apy") or 0.0

        # Filter by Tier-1 protocol
        if not is_tier1_protocol(project):
            continue

        # Filter by Chain
        if chain not in ALLOWED_CHAINS:
            continue

        # Filter by Minimum TVL ($1M+)
        if tvl < min_tvl:
            continue

        # Sanity check on extreme APYs
        if apy < 0 or apy > 1000:
            continue

        pool_id = item.get("pool")
        if not pool_id:
            continue

        records.append({
            "ts": now_iso,
            "pool_id": pool_id,
            "project": item.get("project"),
            "chain": item.get("chain"),
            "symbol": item.get("symbol", "").upper(),
            "tvl_usd": tvl,
            "apy": apy,
            "apy_base": item.get("apyBase") or 0.0,
            "apy_reward": item.get("apyReward") or 0.0,
            "apy_mean_30d": item.get("apyMean30d") or 0.0,
            "utilization": None
        })

    inserted = insert_snapshots(records, db_path=db_path)
    print(f"[Worker] Ingested {len(records)} Tier-1 snapshots ({inserted} rows saved to DB)")
    return records


def bootstrap_pool_history(pool_id: str, db_path: Optional[str] = None) -> int:
    """
    Backfill historical chart points for a specific pool using DefiLlama chart API.
    Used on initial start to instantly populate 30-day history.
    """
    url = f"https://yields.llama.fi/chart/{pool_id}"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return 0

        # Find pool metadata from latest snapshot or first item
        conn = get_connection(db_path)
        cur = conn.cursor()
        cur.execute("SELECT project, chain, symbol FROM snapshots WHERE pool_id = ? LIMIT 1", (pool_id,))
        row = cur.fetchone()
        project = row["project"] if row else "unknown"
        chain = row["chain"] if row else "Ethereum"
        symbol = row["symbol"] if row else "LP"
        conn.close()

        records = []
        for point in data[-30:]:  # Last 30 daily data points
            ts_str = point.get("timestamp")
            if not ts_str:
                continue
            records.append({
                "ts": ts_str,
                "pool_id": pool_id,
                "project": project,
                "chain": chain,
                "symbol": symbol,
                "tvl_usd": point.get("tvlUsd") or 0.0,
                "apy": point.get("apy") or 0.0,
                "apy_base": point.get("apyBase") or 0.0,
                "apy_reward": point.get("apyReward") or 0.0,
                "apy_mean_30d": point.get("apy") or 0.0,
                "utilization": None
            })

        inserted = insert_snapshots(records, db_path=db_path)
        return inserted
    except Exception as e:
        print(f"[Worker] History bootstrap failed for {pool_id}: {e}")
        return 0


def bootstrap_top_pools_history(top_n: int = 15, db_path: Optional[str] = None):
    """Bootstrap 30-day historical chart data for top N highest TVL pools."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
    SELECT pool_id, tvl_usd FROM snapshots
    GROUP BY pool_id
    ORDER BY MAX(tvl_usd) DESC
    LIMIT ?
    """, (top_n,))
    rows = cur.fetchall()
    conn.close()

    print(f"[Worker] Bootstrapping history for top {len(rows)} pools...")
    for row in rows:
        pid = row["pool_id"]
        cnt = bootstrap_pool_history(pid, db_path=db_path)
        print(f"  -> {pid}: {cnt} historical points backfilled")
        time.sleep(0.2)  # courteous delay


if __name__ == "__main__":
    records = fetch_and_store_snapshots()
    if records:
        bootstrap_top_pools_history(top_n=10)
