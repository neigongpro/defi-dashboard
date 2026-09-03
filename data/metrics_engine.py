"""
Metrics & Analytics Engine.
Calculates APY 1d/7d/30d moving averages, TVL deltas, APY Stability Score,
Real Yield Ratio, Spike Alert detection, and risk indicators.
"""

import os
import sys
import math
from typing import List, Dict, Any, Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import get_connection, get_latest_snapshots, get_pool_history, get_pool_by_id


def compute_stability_score(apys: List[float]) -> float:
    """
    Calculate APY Stability Score from 0.0 (erratic/volatile) to 1.0 (rock-solid).
    Uses Coefficient of Variation: CV = std_dev / mean.
    Stability = max(0.0, min(1.0, 1.0 - CV * 0.5))
    """
    if not apys or len(apys) < 2:
        return 0.9  # Default high stability for newly tracked pools

    mean_apy = sum(apys) / len(apys)
    if mean_apy <= 0.1:
        return 0.5

    variance = sum((x - mean_apy) ** 2 for x in apys) / len(apys)
    std_dev = math.sqrt(variance)
    cv = std_dev / mean_apy

    score = 1.0 - (cv * 0.5)
    return round(max(0.0, min(1.0, score)), 2)


def calculate_pool_metrics(pool_id: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate comprehensive metrics for a specific pool using historical time series.
    """
    history = get_pool_history(pool_id, days=30, db_path=db_path)
    latest = get_pool_by_id(pool_id, db_path=db_path)

    if not latest:
        return {}

    cur_apy = float(latest["apy"] or 0.0)
    cur_base = float(latest["apy_base"] or 0.0)
    cur_reward = float(latest["apy_reward"] or 0.0)
    cur_tvl = float(latest["tvl_usd"] or 0.0)
    mean_30d_precomputed = float(latest["apy_mean_30d"] or cur_apy)

    # If we have historical points, compute empirical statistics
    if history:
        apys_all = [float(h["apy"]) for h in history]
        apys_7d = apys_all[-7:] if len(apys_all) >= 7 else apys_all
        avg_7d = sum(apys_7d) / len(apys_7d)
        avg_30d = sum(apys_all) / len(apys_all) if len(apys_all) >= 10 else mean_30d_precomputed
        stability_score = compute_stability_score(apys_all)

        # 7d TVL delta
        first_tvl = float(history[0]["tvl_usd"]) if history else cur_tvl
        tvl_change_7d_pct = ((cur_tvl - first_tvl) / first_tvl * 100) if first_tvl > 0 else 0.0
    else:
        avg_7d = cur_apy
        avg_30d = mean_30d_precomputed
        stability_score = 0.85
        tvl_change_7d_pct = 0.0

    # Real yield ratio: Base APY / Total APY
    if cur_apy > 0:
        real_yield_ratio = round(min(1.0, max(0.0, cur_base / cur_apy)), 2)
    else:
        real_yield_ratio = 1.0 if cur_base >= 0 else 0.0

    # Spike detector: current APY > 2.2x the 30d average and above 6%
    is_spike = (cur_apy > (avg_30d * 2.2)) and (cur_apy > 6.0)

    # Safety rating based on TVL and stability
    if cur_tvl >= 50_000_000 and stability_score >= 0.7:
        safety_grade = "AAA"
    elif cur_tvl >= 10_000_000 and stability_score >= 0.5:
        safety_grade = "AA"
    elif cur_tvl >= 2_000_000:
        safety_grade = "A"
    else:
        safety_grade = "BBB"

    return {
        "pool_id": pool_id,
        "project": latest["project"],
        "chain": latest["chain"],
        "symbol": latest["symbol"],
        "tvl_usd": cur_tvl,
        "apy": round(cur_apy, 2),
        "apy_base": round(cur_base, 2),
        "apy_reward": round(cur_reward, 2),
        "apy_avg_7d": round(avg_7d, 2),
        "apy_avg_30d": round(avg_30d, 2),
        "tvl_change_7d_pct": round(tvl_change_7d_pct, 2),
        "stability_score": stability_score,
        "real_yield_ratio": real_yield_ratio,
        "is_spike": is_spike,
        "safety_grade": safety_grade,
        "utilization": latest.get("utilization"),
        "ts": latest["ts"]
    }


def get_enriched_pools(
    assets: Optional[List[str]] = None,
    chains: Optional[List[str]] = None,
    protocols: Optional[List[str]] = None,
    category: Optional[str] = None,
    stables_only: bool = False,
    min_tvl: float = 100_000,
    sort_by: str = "apy",
    sort_order: str = "desc",
    limit: int = 100,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all latest pools enriched with calculated analytics metrics and sorted.
    """
    from defi_engine import get_category, get_protocol_url, is_stablecoin, normalize_stable_symbol

    raw_pools = get_latest_snapshots(
        db_path=db_path,
        assets=assets,
        chains=chains,
        protocols=protocols,
        min_tvl=min_tvl,
        limit=max(limit * 3, 300)
    )

    enriched = []
    for p in raw_pools:
        cat = get_category(p["project"], p["symbol"])
        if category and cat != category:
            continue

        # If user asked for stablecoins only, filter out non-stablecoins
        if stables_only and not is_stablecoin(p["symbol"]):
            continue

        # In pure lending mode, strictly exclude any liquidity pair symbols
        if category == "lending" and ("-" in p["symbol"] or "/" in p["symbol"]):
            continue

        cur_apy = float(p["apy"] or 0.0)
        cur_base = float(p["apy_base"] or 0.0)
        cur_reward = float(p["apy_reward"] or 0.0)
        cur_tvl = float(p["tvl_usd"] or 0.0)
        mean_30d = float(p["apy_mean_30d"] or cur_apy)

        real_yield_ratio = round(min(1.0, max(0.0, cur_base / cur_apy)), 2) if cur_apy > 0 else 1.0
        is_spike = (cur_apy > (mean_30d * 2.2)) and (cur_apy > 6.0)

        # Approximate stability using precomputed 30d delta vs current
        diff = abs(cur_apy - mean_30d)
        stability = round(max(0.2, min(1.0, 1.0 - (diff / max(cur_apy, 5.0) * 0.5))), 2)

        if cur_tvl >= 50_000_000 and stability >= 0.7:
            safety_grade = "AAA"
        elif cur_tvl >= 10_000_000 and stability >= 0.5:
            safety_grade = "AA"
        elif cur_tvl >= 2_000_000:
            safety_grade = "A"
        else:
            safety_grade = "BBB"

        clean_sym = normalize_stable_symbol(p["symbol"])
        is_canonical = p["symbol"].upper() in {"USDC", "USDT", "DAI", "USDS", "USDE", "PYUSD", "GHO", "FRAX", "FDUSD", "CRVUSD"}
        proto_url = get_protocol_url(p["project"], p["pool_id"])

        enriched.append({
            "pool_id": p["pool_id"],
            "project": p["project"],
            "chain": p["chain"],
            "symbol": p["symbol"],
            "clean_symbol": clean_sym,
            "is_canonical": is_canonical,
            "protocol_url": proto_url,
            "category": cat,
            "tvl_usd": cur_tvl,
            "apy": round(cur_apy, 2),
            "apy_base": round(cur_base, 2),
            "apy_reward": round(cur_reward, 2),
            "apy_avg_30d": round(mean_30d, 2),
            "real_yield_ratio": real_yield_ratio,
            "is_spike": is_spike,
            "stability_score": stability,
            "safety_grade": safety_grade,
            "ts": p["ts"]
        })

    # Sorting
    is_reverse = (sort_order.lower() != "asc")
    grade_ranks = {"AAA": 4, "AA": 3, "A": 2, "BBB": 1}

    if sort_by == "tvl":
        enriched.sort(key=lambda x: x["tvl_usd"], reverse=is_reverse)
    elif sort_by in ("apy_avg_30d", "30d", "apy_30d"):
        enriched.sort(key=lambda x: x["apy_avg_30d"], reverse=is_reverse)
    elif sort_by == "stability":
        enriched.sort(key=lambda x: (x["stability_score"], x["apy"]), reverse=is_reverse)
    elif sort_by == "real_yield":
        enriched.sort(key=lambda x: (x["apy_base"], x["tvl_usd"]), reverse=is_reverse)
    elif sort_by == "project":
        enriched.sort(key=lambda x: x["project"].lower(), reverse=is_reverse)
    elif sort_by == "symbol":
        enriched.sort(key=lambda x: (x.get("clean_symbol") or x["symbol"]).lower(), reverse=is_reverse)
    elif sort_by in ("category", "type"):
        enriched.sort(key=lambda x: x["category"].lower(), reverse=is_reverse)
    elif sort_by in ("rating", "safety", "safety_grade"):
        enriched.sort(key=lambda x: (0 if x["is_spike"] else grade_ranks.get(x["safety_grade"], 1), x["tvl_usd"]), reverse=is_reverse)
    elif sort_by == "chain":
        enriched.sort(key=lambda x: x["chain"].lower(), reverse=is_reverse)
    else:  # default apy
        enriched.sort(key=lambda x: x["apy"], reverse=is_reverse)

    return enriched[:limit]


def get_market_overview(stables_only: bool = False, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Calculate high-level market summary for dashboard top cards."""
    all_pools = get_enriched_pools(min_tvl=100_000, limit=300, stables_only=stables_only, db_path=db_path)
    if not all_pools:
        return {
            "total_tvl_monitored": 0,
            "total_pools_count": 0,
            "avg_stable_apy": 0.0,
            "avg_eth_apy": 0.0,
            "top_safe_yield": None
        }

    total_tvl = sum(p["tvl_usd"] for p in all_pools)
    stables = [p["apy"] for p in all_pools if any(s in p["symbol"].upper() for s in ["USDC", "USDT", "DAI", "USDS", "USDE", "PYUSD"])]
    eth_pools = [p["apy"] for p in all_pools if any(s in p["symbol"].upper() for s in ["ETH", "WETH", "STETH"])]

    avg_stable = (sum(stables) / len(stables)) if stables else 0.0
    avg_eth = (sum(eth_pools) / len(eth_pools)) if eth_pools else 0.0

    safe_pools = [p for p in all_pools if p["safety_grade"] in ("AAA", "AA") and not p["is_spike"]]
    top_safe = safe_pools[0] if safe_pools else (all_pools[0] if all_pools else None)

    return {
        "total_tvl_monitored": total_tvl,
        "total_pools_count": len(all_pools),
        "avg_stable_apy": round(avg_stable, 2),
        "avg_eth_apy": round(avg_eth, 2),
        "top_safe_yield": top_safe
    }


if __name__ == "__main__":
    overview = get_market_overview()
    print("Market Overview:", overview)
    top_stables = get_enriched_pools(assets=["USDC", "USDT"], category="lending", limit=5)
    print("\nTop 5 Stable Lending Pools:")
    for p in top_stables:
        print(f"  {p['project']} ({p['chain']}) - {p['symbol']}: {p['apy']}% (Base: {p['apy_base']}%) | TVL: ${p['tvl_usd']:,.0f} | Safety: {p['safety_grade']}")
