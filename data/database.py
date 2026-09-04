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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_portfolio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT 'default_user',
        protocol TEXT NOT NULL,
        chain TEXT NOT NULL,
        asset TEXT NOT NULL,
        amount_usd REAL NOT NULL,
        current_apy REAL DEFAULT 0.0,
        pool_id TEXT,
        notes TEXT,
        position_type TEXT DEFAULT 'lending',
        entry_date TEXT DEFAULT NULL,
        entry_price_a REAL DEFAULT 0.0,
        entry_price_b REAL DEFAULT 0.0,
        entry_amount_a REAL DEFAULT 0.0,
        entry_amount_b REAL DEFAULT 0.0,
        current_amount_a REAL DEFAULT 0.0,
        current_amount_b REAL DEFAULT 0.0,
        current_price_a REAL DEFAULT 0.0,
        current_price_b REAL DEFAULT 0.0,
        fee_earnings_usd REAL DEFAULT 0.0,
        borrow_debt_usd REAL DEFAULT 0.0,
        impermanent_loss_usd REAL DEFAULT 0.0,
        net_pnl_usd REAL DEFAULT 0.0,
        asset_c TEXT DEFAULT NULL,
        entry_amount_c REAL DEFAULT 0.0,
        entry_price_c REAL DEFAULT 0.0,
        current_amount_c REAL DEFAULT 0.0,
        current_price_c REAL DEFAULT 0.0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_portfolio_uid ON user_portfolio(user_id);")

    # Dynamic schema migration for existing user_portfolio tables
    cursor.execute("PRAGMA table_info(user_portfolio)")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    portfolio_extra_cols = [
        ("position_type", "TEXT DEFAULT 'lending'"),
        ("entry_date", "TEXT DEFAULT NULL"),
        ("entry_price_a", "REAL DEFAULT 0.0"),
        ("entry_price_b", "REAL DEFAULT 0.0"),
        ("entry_amount_a", "REAL DEFAULT 0.0"),
        ("entry_amount_b", "REAL DEFAULT 0.0"),
        ("current_amount_a", "REAL DEFAULT 0.0"),
        ("current_amount_b", "REAL DEFAULT 0.0"),
        ("current_price_a", "REAL DEFAULT 0.0"),
        ("current_price_b", "REAL DEFAULT 0.0"),
        ("fee_earnings_usd", "REAL DEFAULT 0.0"),
        ("borrow_debt_usd", "REAL DEFAULT 0.0"),
        ("impermanent_loss_usd", "REAL DEFAULT 0.0"),
        ("net_pnl_usd", "REAL DEFAULT 0.0"),
        ("asset_c", "TEXT DEFAULT NULL"),
        ("entry_amount_c", "REAL DEFAULT 0.0"),
        ("entry_price_c", "REAL DEFAULT 0.0"),
        ("current_amount_c", "REAL DEFAULT 0.0"),
        ("current_price_c", "REAL DEFAULT 0.0"),
    ]
    for col_name, col_def in portfolio_extra_cols:
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE user_portfolio ADD COLUMN {col_name} {col_def};")
            except Exception:
                pass
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


# ──────────────────────────────────────────────
#  USER PORTFOLIO (Личный Кабинет) STORAGE
# ──────────────────────────────────────────────

def calculate_position_math(pos: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate PnL, accrued yield, borrow debt, and impermanent loss for a position."""
    pos_type = (pos.get("position_type") or "lending").lower()
    entry_date_str = pos.get("entry_date")
    apy = float(pos.get("current_apy") or 0.0)
    amount_usd = float(pos.get("amount_usd") or 0.0)

    days_held = 0
    if entry_date_str:
        try:
            clean_date = entry_date_str.split("T")[0]
            dt = datetime.strptime(clean_date, "%Y-%m-%d")
            now = datetime.now()
            days_held = max(0, (now - dt).days)
        except Exception:
            days_held = 0

    fee_earnings = float(pos.get("fee_earnings_usd") or 0.0)
    borrow_debt = float(pos.get("borrow_debt_usd") or 0.0)
    il_usd = float(pos.get("impermanent_loss_usd") or 0.0)

    if pos_type == "lending":
        earned_yield = amount_usd * (apy / 100.0) * (days_held / 365.0) if days_held > 0 else 0.0
        if fee_earnings > 0:
            earned_yield += fee_earnings
        pos["earned_yield_usd"] = round(earned_yield, 2)
        pos["current_value_usd"] = round(amount_usd + earned_yield, 2)
        pos["net_pnl_usd"] = round(earned_yield, 2)
        pos["net_pnl_pct"] = round((earned_yield / amount_usd * 100.0), 2) if amount_usd > 0 else 0.0
        pos["borrow_debt_usd"] = 0.0
        pos["impermanent_loss_usd"] = 0.0

        # Token math
        cur_price = float(pos.get("current_price_a") or pos.get("entry_price_a") or 0.0)
        entry_amt = float(pos.get("entry_amount_a") or 0.0)
        if cur_price <= 0 and entry_amt > 0 and amount_usd > 0:
            cur_price = amount_usd / entry_amt
        if cur_price <= 0 and (pos.get("asset") or "").upper() in ("USDT", "USDC", "DAI", "USDS", "PYUSD", "GHO", "FRAX", "FDUSD", "CRVUSD"):
            cur_price = 1.0

        if cur_price > 0:
            pos["current_price_a"] = round(cur_price, 4)
            pos["earned_yield_tokens"] = round(earned_yield / cur_price, 4)
            pos["current_amount_a"] = round((amount_usd + earned_yield) / cur_price, 4)
        else:
            pos["earned_yield_tokens"] = 0.0

    elif pos_type == "borrow":
        accrued_debt = amount_usd * (apy / 100.0) * (days_held / 365.0) if days_held > 0 else 0.0
        total_debt = accrued_debt + borrow_debt
        pos["borrow_debt_usd"] = round(total_debt, 2)
        pos["current_value_usd"] = round(amount_usd, 2)
        pos["net_pnl_usd"] = round(-total_debt, 2)
        pos["net_pnl_pct"] = round(-(total_debt / amount_usd * 100.0), 2) if amount_usd > 0 else 0.0
        pos["earned_yield_usd"] = 0.0
        pos["impermanent_loss_usd"] = 0.0

        # Token math
        cur_price = float(pos.get("current_price_a") or pos.get("entry_price_a") or 0.0)
        entry_amt = float(pos.get("entry_amount_a") or 0.0)
        if cur_price <= 0 and entry_amt > 0 and amount_usd > 0:
            cur_price = amount_usd / entry_amt
        if cur_price <= 0 and (pos.get("asset") or "").upper() in ("USDT", "USDC", "DAI", "USDS", "PYUSD", "GHO", "FRAX", "FDUSD", "CRVUSD"):
            cur_price = 1.0

        if cur_price > 0:
            pos["current_price_a"] = round(cur_price, 4)
            pos["borrow_debt_tokens"] = round(total_debt / cur_price, 4)
            pos["current_amount_a"] = round((amount_usd + total_debt) / cur_price, 4)
        else:
            pos["borrow_debt_tokens"] = 0.0

    elif pos_type in ("liquidity_pool", "lp"):
        entry_a = float(pos.get("entry_amount_a") or 0.0)
        price_a = float(pos.get("entry_price_a") or 0.0)
        entry_b = float(pos.get("entry_amount_b") or 0.0)
        price_b = float(pos.get("entry_price_b") or 0.0)
        entry_c = float(pos.get("entry_amount_c") or 0.0)
        price_c = float(pos.get("entry_price_c") or 0.0)

        cur_a = float(pos.get("current_amount_a") or entry_a)
        cur_price_a = float(pos.get("current_price_a") or price_a)
        cur_b = float(pos.get("current_amount_b") or entry_b)
        cur_price_b = float(pos.get("current_price_b") or price_b)
        cur_c = float(pos.get("current_amount_c") or entry_c)
        cur_price_c = float(pos.get("current_price_c") or price_c)

        initial_val = (entry_a * price_a) + (entry_b * price_b) + (entry_c * price_c)
        if initial_val <= 0:
            initial_val = amount_usd

        current_val = (cur_a * cur_price_a) + (cur_b * cur_price_b) + (cur_c * cur_price_c)
        if current_val <= 0:
            current_val = initial_val

        hodl_val = (entry_a * cur_price_a) + (entry_b * cur_price_b) + (entry_c * cur_price_c)
        if hodl_val <= 0:
            hodl_val = initial_val

        calc_il = max(0.0, hodl_val - current_val)
        if il_usd <= 0 and calc_il > 0:
            il_usd = calc_il

        if fee_earnings <= 0 and days_held > 0 and apy > 0:
            fee_earnings = initial_val * (apy / 100.0) * (days_held / 365.0)

        calc_net_pnl = (current_val + fee_earnings) - initial_val
        net_pnl_pct = (calc_net_pnl / initial_val * 100.0) if initial_val > 0 else 0.0

        pos["initial_value_usd"] = round(initial_val, 2)
        pos["current_value_usd"] = round(current_val, 2)
        pos["hodl_value_usd"] = round(hodl_val, 2)
        pos["fee_earnings_usd"] = round(fee_earnings, 2)
        pos["impermanent_loss_usd"] = round(il_usd, 2)
        pos["net_pnl_usd"] = round(calc_net_pnl, 2)
        pos["net_pnl_pct"] = round(net_pnl_pct, 2)
        pos["earned_yield_usd"] = round(fee_earnings, 2)
        pos["amount_usd"] = round(current_val, 2)

    pos["days_held"] = days_held
    return pos


def get_user_portfolio(user_id: str = "default_user", db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all capital positions for a user with calculated metrics."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT *
    FROM user_portfolio
    WHERE user_id = ?
    ORDER BY amount_usd DESC, id DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    positions = [calculate_position_math(dict(r)) for r in rows]
    return positions


def add_portfolio_position(
    user_id: str = "default_user",
    protocol: str = "",
    chain: str = "",
    asset: str = "",
    amount_usd: float = 0.0,
    current_apy: float = 0.0,
    pool_id: Optional[str] = None,
    notes: Optional[str] = None,
    position_type: str = "lending",
    entry_date: Optional[str] = None,
    entry_price_a: float = 0.0,
    entry_price_b: float = 0.0,
    entry_amount_a: float = 0.0,
    entry_amount_b: float = 0.0,
    current_amount_a: float = 0.0,
    current_amount_b: float = 0.0,
    current_price_a: float = 0.0,
    current_price_b: float = 0.0,
    fee_earnings_usd: float = 0.0,
    borrow_debt_usd: float = 0.0,
    impermanent_loss_usd: float = 0.0,
    net_pnl_usd: float = 0.0,
    asset_c: Optional[str] = None,
    entry_amount_c: float = 0.0,
    entry_price_c: float = 0.0,
    current_amount_c: float = 0.0,
    current_price_c: float = 0.0,
    db_path: Optional[str] = None
) -> int:
    """Insert a new capital position for a user and return its ID."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Calculate initial math if LP or dates provided
    computed_amount = float(amount_usd or 0.0)
    if position_type in ("liquidity_pool", "lp") and computed_amount <= 0:
        computed_amount = (float(entry_amount_a or 0.0) * float(entry_price_a or 0.0)) + (float(entry_amount_b or 0.0) * float(entry_price_b or 0.0)) + (float(entry_amount_c or 0.0) * float(entry_price_c or 0.0))
    elif computed_amount <= 0 and float(entry_amount_a or 0.0) > 0 and float(entry_price_a or 0.0) > 0:
        computed_amount = float(entry_amount_a) * float(entry_price_a)

    cursor.execute("""
    INSERT INTO user_portfolio (
        user_id, protocol, chain, asset, amount_usd, current_apy, pool_id, notes,
        position_type, entry_date,
        entry_price_a, entry_price_b, entry_amount_a, entry_amount_b,
        current_amount_a, current_amount_b, current_price_a, current_price_b,
        fee_earnings_usd, borrow_debt_usd, impermanent_loss_usd, net_pnl_usd,
        asset_c, entry_amount_c, entry_price_c, current_amount_c, current_price_c,
        created_at, updated_at
    ) VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?,
        ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        datetime('now'), datetime('now')
    )
    """, (
        user_id,
        protocol.strip(),
        chain.strip(),
        asset.strip().upper(),
        computed_amount,
        float(current_apy),
        pool_id.strip() if pool_id else None,
        notes.strip() if notes else None,
        (position_type or "lending").strip().lower(),
        entry_date.strip() if entry_date else None,
        float(entry_price_a or 0.0),
        float(entry_price_b or 0.0),
        float(entry_amount_a or 0.0),
        float(entry_amount_b or 0.0),
        float(current_amount_a or entry_amount_a or 0.0),
        float(current_amount_b or entry_amount_b or 0.0),
        float(current_price_a or entry_price_a or 0.0),
        float(current_price_b or entry_price_b or 0.0),
        float(fee_earnings_usd or 0.0),
        float(borrow_debt_usd or 0.0),
        float(impermanent_loss_usd or 0.0),
        float(net_pnl_usd or 0.0),
        asset_c.strip().upper() if asset_c else None,
        float(entry_amount_c or 0.0),
        float(entry_price_c or 0.0),
        float(current_amount_c or 0.0),
        float(current_price_c or 0.0),
    ))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_portfolio_position(
    pos_id: int,
    user_id: str = "default_user",
    protocol: Optional[str] = None,
    chain: Optional[str] = None,
    asset: Optional[str] = None,
    amount_usd: Optional[float] = None,
    current_apy: Optional[float] = None,
    notes: Optional[str] = None,
    position_type: Optional[str] = None,
    entry_date: Optional[str] = None,
    entry_price_a: Optional[float] = None,
    entry_price_b: Optional[float] = None,
    entry_amount_a: Optional[float] = None,
    entry_amount_b: Optional[float] = None,
    current_amount_a: Optional[float] = None,
    current_amount_b: Optional[float] = None,
    current_price_a: Optional[float] = None,
    current_price_b: Optional[float] = None,
    fee_earnings_usd: Optional[float] = None,
    borrow_debt_usd: Optional[float] = None,
    impermanent_loss_usd: Optional[float] = None,
    net_pnl_usd: Optional[float] = None,
    asset_c: Optional[str] = None,
    entry_amount_c: Optional[float] = None,
    entry_price_c: Optional[float] = None,
    current_amount_c: Optional[float] = None,
    current_price_c: Optional[float] = None,
    db_path: Optional[str] = None
) -> bool:
    """Update an existing portfolio position."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    fields = []
    values = []
    if protocol is not None:
        fields.append("protocol = ?")
        values.append(protocol.strip())
    if chain is not None:
        fields.append("chain = ?")
        values.append(chain.strip())
    if asset is not None:
        fields.append("asset = ?")
        values.append(asset.strip().upper())
    if amount_usd is not None:
        fields.append("amount_usd = ?")
        values.append(float(amount_usd))
    if current_apy is not None:
        fields.append("current_apy = ?")
        values.append(float(current_apy))
    if notes is not None:
        fields.append("notes = ?")
        values.append(notes.strip())
    if position_type is not None:
        fields.append("position_type = ?")
        values.append(position_type.strip().lower())
    if entry_date is not None:
        fields.append("entry_date = ?")
        values.append(entry_date.strip())
    if entry_price_a is not None:
        fields.append("entry_price_a = ?")
        values.append(float(entry_price_a))
    if entry_price_b is not None:
        fields.append("entry_price_b = ?")
        values.append(float(entry_price_b))
    if entry_amount_a is not None:
        fields.append("entry_amount_a = ?")
        values.append(float(entry_amount_a))
    if entry_amount_b is not None:
        fields.append("entry_amount_b = ?")
        values.append(float(entry_amount_b))
    if current_amount_a is not None:
        fields.append("current_amount_a = ?")
        values.append(float(current_amount_a))
    if current_amount_b is not None:
        fields.append("current_amount_b = ?")
        values.append(float(current_amount_b))
    if current_price_a is not None:
        fields.append("current_price_a = ?")
        values.append(float(current_price_a))
    if current_price_b is not None:
        fields.append("current_price_b = ?")
        values.append(float(current_price_b))
    if fee_earnings_usd is not None:
        fields.append("fee_earnings_usd = ?")
        values.append(float(fee_earnings_usd))
    if borrow_debt_usd is not None:
        fields.append("borrow_debt_usd = ?")
        values.append(float(borrow_debt_usd))
    if impermanent_loss_usd is not None:
        fields.append("impermanent_loss_usd = ?")
        values.append(float(impermanent_loss_usd))
    if net_pnl_usd is not None:
        fields.append("net_pnl_usd = ?")
        values.append(float(net_pnl_usd))
    if asset_c is not None:
        fields.append("asset_c = ?")
        values.append(asset_c.strip().upper())
    if entry_amount_c is not None:
        fields.append("entry_amount_c = ?")
        values.append(float(entry_amount_c))
    if entry_price_c is not None:
        fields.append("entry_price_c = ?")
        values.append(float(entry_price_c))
    if current_amount_c is not None:
        fields.append("current_amount_c = ?")
        values.append(float(current_amount_c))
    if current_price_c is not None:
        fields.append("current_price_c = ?")
        values.append(float(current_price_c))

    if not fields:
        conn.close()
        return False

    fields.append("updated_at = datetime('now')")
    values.extend([pos_id, user_id])

    query = f"UPDATE user_portfolio SET {', '.join(fields)} WHERE id = ? AND user_id = ?"
    cursor.execute(query, tuple(values))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def delete_portfolio_position(pos_id: int, user_id: str = "default_user", db_path: Optional[str] = None) -> bool:
    """Delete a user position by ID."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_portfolio WHERE id = ? AND user_id = ?", (pos_id, user_id))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_portfolio_summary(user_id: str = "default_user", db_path: Optional[str] = None) -> Dict[str, Any]:
    """Calculate aggregated metrics for a user's portfolio."""
    positions = get_user_portfolio(user_id=user_id, db_path=db_path)
    
    total_supply = 0.0
    total_borrow = 0.0
    total_yield = 0.0
    total_fees = 0.0
    total_pnl = 0.0
    earning_capital = 0.0
    earning_product = 0.0

    for p in positions:
        ptype = (p.get("position_type") or "lending").lower()
        cur_val = float(p.get("current_value_usd") or p.get("amount_usd") or 0.0)
        apy = float(p.get("current_apy") or 0.0)

        if ptype == "borrow":
            debt = float(p.get("amount_usd") or 0.0) + float(p.get("borrow_debt_usd") or 0.0)
            total_borrow += debt
            total_pnl += float(p.get("net_pnl_usd") or 0.0)
        else:
            # lending or liquidity_pool
            total_supply += cur_val
            earning_capital += cur_val
            earning_product += cur_val * apy
            total_yield += float(p.get("earned_yield_usd") or 0.0)
            if ptype in ("liquidity_pool", "lp"):
                total_fees += float(p.get("fee_earnings_usd") or 0.0)
            total_pnl += float(p.get("net_pnl_usd") or 0.0)

    weighted_apy = (earning_product / earning_capital) if earning_capital > 0 else 0.0
    annual_income = earning_capital * (weighted_apy / 100.0)
    monthly_income = annual_income / 12.0
    net_capital = total_supply - total_borrow

    return {
        "positions_count": len(positions),
        "total_capital": round(total_supply if total_supply > 0 else sum(p["amount_usd"] for p in positions), 2),
        "total_supply_usd": round(total_supply, 2),
        "total_borrow_usd": round(total_borrow, 2),
        "net_capital_usd": round(net_capital, 2),
        "total_yield_earned": round(total_yield, 2),
        "total_fee_earnings": round(total_fees, 2),
        "total_net_pnl": round(total_pnl, 2),
        "weighted_apy": round(weighted_apy, 2),
        "monthly_income": round(monthly_income, 2),
        "annual_income": round(annual_income, 2)
    }


DEFAULT_CHAINS = [
    "Ethereum", "Base", "Arbitrum", "Optimism", "Polygon", "BSC", "Avalanche",
    "Solana", "Sui", "Aptos", "Sonic", "Fraxtal", "Plasma", "Linea", "Mantle",
    "Scroll", "Fantom", "Gnosis", "Celo", "Blast", "Sei", "Tron", "Berachain",
    "zkSync Era", "Hyperliquid L1", "Unichain", "Near", "TON"
]

DEFAULT_PROTOCOLS = [
    "Aave v3", "Morpho Blue", "Spark", "Fluid", "Compound v3", "Uniswap v3",
    "Curve", "Aerodrome", "Velodrome", "Kamino", "Raydium", "Orca",
    "Navi Protocol", "Scallop", "Cetus", "Pendle", "Lido", "Ethena",
    "Ether.fi", "Jito", "Thala", "Aries Markets", "Frax", "Venus", "Benqi",
    "Silo v2", "Camelot v3", "Balancer v2"
]

DEFAULT_ASSETS = [
    "USDT", "USDC", "DAI", "USDS", "USDE", "PYUSD", "GHO", "FRAX", "FDUSD", "CRVUSD",
    "ETH", "WETH", "WBTC", "cbBTC", "SOL", "SUI", "APT", "AVAX", "BNB", "POL", "S"
]

def get_distinct_chains(db_path: Optional[str] = None) -> List[str]:
    """Return all unique chains monitored on the dashboard, combined with standard Tier-1 chains."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT chain FROM snapshots WHERE chain IS NOT NULL AND chain != ''")
    db_chains = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()

    chain_map = {}
    for c in DEFAULT_CHAINS + db_chains:
        normalized = c.strip().capitalize()
        for known in DEFAULT_CHAINS:
            if c.strip().lower() == known.lower():
                normalized = known
                break
        if normalized.lower() not in chain_map:
            chain_map[normalized.lower()] = normalized
    return sorted(chain_map.values(), key=lambda x: x.lower())


def get_distinct_protocols(db_path: Optional[str] = None) -> List[str]:
    """Return all unique protocols monitored on the dashboard, combined with standard Tier-1 protocols."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT project FROM snapshots WHERE project IS NOT NULL AND project != ''")
    db_protocols = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()

    proto_map = {}
    for p in DEFAULT_PROTOCOLS + db_protocols:
        name = p.strip()
        proto_map[name.lower()] = name
    return sorted(proto_map.values(), key=lambda x: x.lower())


def get_distinct_assets(db_path: Optional[str] = None) -> List[str]:
    """Return all unique assets/symbols monitored on the dashboard."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT symbol FROM snapshots WHERE symbol IS NOT NULL AND symbol != ''")
    db_assets = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()

    asset_map = {}
    for a in DEFAULT_ASSETS + db_assets:
        clean = a.strip().upper()
        if clean not in asset_map:
            asset_map[clean] = clean
    return sorted(asset_map.values())


def search_pools_for_autocomplete(
    q: str = "",
    chain: Optional[str] = None,
    protocol: Optional[str] = None,
    limit: int = 30,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search snapshots for pools matching asset/symbol, chain, or protocol with real-time rates."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    query = """
    WITH Ranked AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY pool_id ORDER BY ts DESC) as rn
        FROM snapshots
    )
    SELECT pool_id, project, chain, symbol, tvl_usd, apy, apy_base, apy_reward
    FROM Ranked
    WHERE rn = 1
    """
    params: List[Any] = []
    if chain:
        query += " AND LOWER(chain) = ?"
        params.append(chain.lower().strip())
    if protocol:
        query += " AND LOWER(project) LIKE ?"
        params.append(f"%{protocol.lower().strip()}%")
    if q:
        term = f"%{q.lower().strip()}%"
        query += " AND (LOWER(symbol) LIKE ? OR LOWER(chain) LIKE ? OR LOWER(project) LIKE ?)"
        params.extend([term, term, term])

    query += " ORDER BY tvl_usd DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

