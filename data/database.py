"""
Database management module for DeFi Yield & Rebalance Dashboard.
Uses SQLite for zero-cost, lightweight, single-file persistent storage.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "defi_dashboard.db")


_initialized_dbs = set()

def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create and configure a SQLite connection with row factory and auto-init."""
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")

    if path not in _initialized_dbs:
        _init_db_conn(conn)
        _initialized_dbs.add(path)

    return conn


def _init_db_conn(conn: sqlite3.Connection) -> None:
    """Internal helper to initialize SQLite tables and indexes on an open connection."""
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts DATETIME NOT NULL,
        pool_id TEXT NOT NULL,
        project TEXT NOT NULL,
        chain TEXT NOT NULL,
        symbol TEXT NOT NULL,
        tvl_usd REAL NOT NULL,
        apy REAL NOT NULL,
        apy_base REAL DEFAULT 0.0,
        apy_reward REAL DEFAULT 0.0,
        apy_mean_30d REAL DEFAULT 0.0,
        utilization REAL DEFAULT NULL
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_snap_pool_ts ON snapshots(pool_id, ts);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_snap_project ON snapshots(project);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_snap_ts ON snapshots(ts);")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_rollups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,
        pool_id TEXT NOT NULL,
        project TEXT NOT NULL,
        chain TEXT NOT NULL,
        symbol TEXT NOT NULL,
        tvl_avg REAL NOT NULL,
        tvl_min REAL,
        tvl_max REAL,
        apy_avg REAL NOT NULL,
        apy_min REAL,
        apy_max REAL,
        apy_base_avg REAL DEFAULT 0.0,
        apy_reward_avg REAL DEFAULT 0.0,
        samples INTEGER NOT NULL,
        UNIQUE(date, pool_id)
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rollup_pool_date ON daily_rollups(pool_id, date);")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        asset TEXT NOT NULL,
        amount_usd REAL NOT NULL,
        protocol TEXT NOT NULL,
        chain TEXT NOT NULL,
        pool_id TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_pos ON user_positions(user_id);")
    conn.commit()


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize SQLite tables and indexes."""
    conn = get_connection(db_path)
    conn.close()


def insert_snapshots(records: List[Dict[str, Any]], db_path: Optional[str] = None) -> int:
    """Batch insert snapshots into SQLite."""
    if not records:
        return 0

    conn = get_connection(db_path)
    cursor = conn.cursor()

    now_iso = datetime.now(timezone.utc).isoformat()
    rows = []
    for r in records:
        ts = r.get("ts", now_iso)
        rows.append((
            ts,
            r["pool_id"],
            r["project"],
            r["chain"],
            r["symbol"],
            float(r.get("tvl_usd", 0.0)),
            float(r.get("apy", 0.0)),
            float(r.get("apy_base", 0.0) or 0.0),
            float(r.get("apy_reward", 0.0) or 0.0),
            float(r.get("apy_mean_30d", 0.0) or 0.0),
            r.get("utilization")
        ))

    cursor.executemany("""
    INSERT INTO snapshots (
        ts, pool_id, project, chain, symbol, tvl_usd, apy,
        apy_base, apy_reward, apy_mean_30d, utilization
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    conn.commit()
    inserted_count = cursor.rowcount
    conn.close()
    return inserted_count


def get_latest_snapshots(
    db_path: Optional[str] = None,
    assets: Optional[List[str]] = None,
    chains: Optional[List[str]] = None,
    protocols: Optional[List[str]] = None,
    min_tvl: float = 1_000_000,
    limit: int = 150
) -> List[Dict[str, Any]]:
    """
    Get the most recent snapshot for each pool with optional filtering.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    query = """
    WITH Ranked AS (
        SELECT 
            *,
            ROW_NUMBER() OVER (PARTITION BY pool_id ORDER BY ts DESC) as rn
        FROM snapshots
    )
    SELECT 
        id, ts, pool_id, project, chain, symbol, tvl_usd, apy,
        apy_base, apy_reward, apy_mean_30d, utilization
    FROM Ranked
    WHERE rn = 1 AND tvl_usd >= ?
    """
    params: List[Any] = [min_tvl]

    if protocols:
        placeholders = ",".join("?" for _ in protocols)
        query += f" AND LOWER(project) IN ({placeholders})"
        params.extend([p.lower() for p in protocols])

    if chains:
        placeholders = ",".join("?" for _ in chains)
        query += f" AND LOWER(chain) IN ({placeholders})"
        params.extend([c.lower() for c in chains])

    if assets:
        # Match symbol contains any of the assets
        asset_conditions = []
        for a in assets:
            asset_conditions.append("UPPER(symbol) LIKE ?")
            params.append(f"%{a.upper()}%")
        query += f" AND ({' OR '.join(asset_conditions)})"

    query += " ORDER BY apy DESC LIMIT ?"
    # Fetch ample candidates so python-level category and risk filtering has full breadth
    params.append(max(limit * 10, 500))

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        results.append(dict(row))

    return results


def get_pool_history(
    pool_id: str,
    days: int = 30,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve historical data points for a specific pool.
    Combines daily_rollups (if older than 30d) and recent 15-min snapshots.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Fetch recent snapshots
    cursor.execute("""
    SELECT ts, tvl_usd, apy, apy_base, apy_reward, utilization
    FROM snapshots
    WHERE pool_id = ? AND ts >= ?
    ORDER BY ts ASC
    """, (pool_id, cutoff))
    snapshot_rows = cursor.fetchall()

    history = []
    for r in snapshot_rows:
        history.append({
            "timestamp": r["ts"],
            "tvl_usd": r["tvl_usd"],
            "apy": r["apy"],
            "apy_base": r["apy_base"],
            "apy_reward": r["apy_reward"],
            "utilization": r["utilization"],
            "type": "snapshot"
        })

    # If not enough snapshot rows or looking back past 30 days, load from daily_rollups
    if days > 30 or len(history) < 10:
        cursor.execute("""
        SELECT date, tvl_avg, apy_avg, apy_base_avg, apy_reward_avg
        FROM daily_rollups
        WHERE pool_id = ? AND date >= ?
        ORDER BY date ASC
        """, (pool_id, cutoff[:10]))
        rollup_rows = cursor.fetchall()

        rollups = []
        for r in rollup_rows:
            rollups.append({
                "timestamp": f"{r['date']}T00:00:00Z",
                "tvl_usd": r["tvl_avg"],
                "apy": r["apy_avg"],
                "apy_base": r["apy_base_avg"],
                "apy_reward": r["apy_reward_avg"],
                "utilization": None,
                "type": "rollup"
            })
        if rollups:
            # Combine rollups before recent snapshots
            history = rollups + history

    conn.close()
    return history


def get_pool_by_id(pool_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get the latest snapshot for a single pool."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM snapshots
    WHERE pool_id = ?
    ORDER BY ts DESC
    LIMIT 1
    """, (pool_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def execute_rollup_cleanup(days_to_keep: int = 30, db_path: Optional[str] = None) -> Dict[str, int]:
    """
    Compress snapshots older than `days_to_keep` into daily_rollups,
    then purge those old raw snapshots.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")

    # Aggregate into daily_rollups
    cursor.execute("""
    INSERT OR REPLACE INTO daily_rollups (
        date, pool_id, project, chain, symbol,
        tvl_avg, tvl_min, tvl_max,
        apy_avg, apy_min, apy_max,
        apy_base_avg, apy_reward_avg,
        samples
    )
    SELECT 
        DATE(ts) as d,
        pool_id,
        project,
        chain,
        symbol,
        AVG(tvl_usd) as tvl_avg,
        MIN(tvl_usd) as tvl_min,
        MAX(tvl_usd) as tvl_max,
        AVG(apy) as apy_avg,
        MIN(apy) as apy_min,
        MAX(apy) as apy_max,
        AVG(apy_base) as apy_base_avg,
        AVG(apy_reward) as apy_reward_avg,
        COUNT(*) as samples
    FROM snapshots
    WHERE DATE(ts) < ?
    GROUP BY DATE(ts), pool_id, project, chain, symbol
    """, (cutoff_date,))
    rollups_created = cursor.rowcount

    # Delete old raw snapshots
    cursor.execute("DELETE FROM snapshots WHERE DATE(ts) < ?", (cutoff_date,))
    deleted_snapshots = cursor.rowcount

    conn.commit()
    conn.close()

    return {
        "rollups_created": rollups_created,
        "snapshots_purged": deleted_snapshots
    }
