"""
Rebalance Advisor Engine.
Evaluates user portfolio positions, scans Tier-1 alternatives,
calculates gas break-even timeframes, and generates structured rebalancing verdicts.
"""

import os
import sys
from typing import Dict, Any, List, Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.metrics_engine import get_enriched_pools

# Estimated gas & transaction costs in USD by chain
CHAIN_GAS_ESTIMATES = {
    "ethereum": {"withdraw": 6.0, "deposit": 8.0, "bridge_out": 7.0},
    "arbitrum": {"withdraw": 0.05, "deposit": 0.08, "bridge_out": 0.50},
    "base": {"withdraw": 0.03, "deposit": 0.05, "bridge_out": 0.30},
    "optimism": {"withdraw": 0.04, "deposit": 0.06, "bridge_out": 0.40},
    "polygon": {"withdraw": 0.02, "deposit": 0.03, "bridge_out": 0.20},
    "bsc": {"withdraw": 0.10, "deposit": 0.15, "bridge_out": 0.50},
    "avalanche": {"withdraw": 0.15, "deposit": 0.20, "bridge_out": 0.60},
    "gnosis": {"withdraw": 0.01, "deposit": 0.02, "bridge_out": 0.20},
    "solana": {"withdraw": 0.005, "deposit": 0.005, "bridge_out": 0.50},
}


def estimate_transfer_gas(from_chain: str, to_chain: str) -> float:
    """Estimate total gas and bridging costs between chains."""
    fc = from_chain.lower()
    tc = to_chain.lower()

    from_cfg = CHAIN_GAS_ESTIMATES.get(fc, {"withdraw": 2.0, "deposit": 2.0, "bridge_out": 2.0})
    to_cfg = CHAIN_GAS_ESTIMATES.get(tc, {"withdraw": 0.1, "deposit": 0.1, "bridge_out": 0.5})

    total = from_cfg["withdraw"] + to_cfg["deposit"]
    if fc != tc:
        total += from_cfg["bridge_out"]

    return round(total, 2)


def evaluate_rebalance(
    asset: str,
    amount_usd: float,
    current_protocol: str,
    current_chain: str,
    current_apy: Optional[float] = None,
    category: str = "lending",
    min_tvl: float = 2_000_000,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluate user position against all Tier-1 pools and calculate rebalancing metrics.
    """
    asset_norm = asset.upper().strip()
    cur_proto_norm = current_protocol.lower().strip()
    cur_chain_norm = current_chain.lower().strip()

    # If current APY not provided, try finding matching pool in database
    if current_apy is None or current_apy <= 0:
        candidates = get_enriched_pools(
            assets=[asset_norm],
            chains=[cur_chain_norm],
            protocols=[cur_proto_norm],
            limit=5,
            db_path=db_path
        )
        current_apy = candidates[0]["apy"] if candidates else 4.0

    current_yearly_usd = amount_usd * (current_apy / 100.0)

    # Scan available Tier-1 alternative pools for the same asset
    all_alternatives = get_enriched_pools(
        assets=[asset_norm],
        category=category if category != "all" else None,
        min_tvl=min_tvl,
        sort_by="apy",
        limit=50,
        db_path=db_path
    )

    valid_candidates: List[Dict[str, Any]] = []

    for pool in all_alternatives:
        p_proj = pool["project"].lower()
        p_chain = pool["chain"].lower()

        # Skip the exact same pool
        if cur_proto_norm in p_proj and cur_chain_norm == p_chain:
            continue

        # Skip erratic spikes or very low stability pools
        if pool["is_spike"] or pool["stability_score"] < 0.4:
            continue

        alt_apy = pool["apy"]
        apy_diff = alt_apy - current_apy

        gas_cost = estimate_transfer_gas(cur_chain_norm, p_chain)
        yearly_extra_usd = amount_usd * (apy_diff / 100.0)
        daily_extra_usd = yearly_extra_usd / 365.0

        if daily_extra_usd > 0:
            break_even_days = round(gas_cost / daily_extra_usd, 1)
        else:
            break_even_days = 9999.0

        valid_candidates.append({
            "pool_id": pool["pool_id"],
            "project": pool["project"],
            "chain": pool["chain"],
            "symbol": pool["symbol"],
            "category": pool["category"],
            "tvl_usd": pool["tvl_usd"],
            "apy": alt_apy,
            "apy_base": pool["apy_base"],
            "apy_reward": pool["apy_reward"],
            "apy_diff": round(apy_diff, 2),
            "safety_grade": pool["safety_grade"],
            "stability_score": pool["stability_score"],
            "gas_cost_usd": gas_cost,
            "break_even_days": break_even_days,
            "yearly_extra_usd": round(yearly_extra_usd, 2),
            "daily_extra_usd": round(daily_extra_usd, 2)
        })

    # Sort candidates by yearly extra profit and break even days
    valid_candidates.sort(key=lambda x: (x["apy_diff"] > 0, -x["break_even_days"] if x["break_even_days"] < 999 else -9999, x["apy_diff"]), reverse=True)

    best_alt = valid_candidates[0] if valid_candidates else None

    # Verdict generation
    if not best_alt or best_alt["apy_diff"] <= 0.3:
        verdict = "HOLD"
        summary = f"Оставить как есть. Ваша ставка {current_apy}% является оптимальной среди надёжных Tier-1 пулов."
    elif best_alt["break_even_days"] <= 14.0 and best_alt["apy_diff"] >= 1.5:
        verdict = "STRONG_MOVE"
        summary = (
            f"Рекомендуем переложить в {best_alt['project']} на сети {best_alt['chain']} "
            f"(+{best_alt['apy_diff']}% APY). Окупаемость газа: {best_alt['break_even_days']} дн., "
            f"дополнительный доход: +${best_alt['yearly_extra_usd']:,.0f}/год."
        )
    elif best_alt["break_even_days"] <= 35.0 and best_alt["apy_diff"] >= 0.8:
        verdict = "CONSIDER"
        summary = (
            f"Можно рассмотреть перенос в {best_alt['project']} ({best_alt['chain']}) "
            f"под {best_alt['apy']}%. Окупаемость: {best_alt['break_even_days']} дн."
        )
    else:
        verdict = "HOLD"
        summary = (
            f"Оставить на месте. Хотя в {best_alt['project']} ставка выше на +{best_alt['apy_diff']}%, "
            f"комиссии за газ окупятся только через {best_alt['break_even_days']} дн., что нецелесообразно."
        )

    return {
        "current_position": {
            "asset": asset_norm,
            "amount_usd": amount_usd,
            "protocol": current_protocol,
            "chain": current_chain,
            "current_apy": current_apy,
            "yearly_yield_usd": round(current_yearly_usd, 2)
        },
        "verdict": verdict,
        "verdict_summary": summary,
        "best_alternative": best_alt,
        "alternatives": valid_candidates[:4]
    }


if __name__ == "__main__":
    result = evaluate_rebalance(
        asset="USDT",
        amount_usd=10000,
        current_protocol="aave-v3",
        current_chain="Ethereum",
        current_apy=4.2
    )
    print("Rebalance Evaluation:")
    print("Verdict:", result["verdict"])
    print("Summary:", result["verdict_summary"])
    if result["best_alternative"]:
        ba = result["best_alternative"]
        print(f"Best: {ba['project']} on {ba['chain']} ({ba['symbol']}) -> APY {ba['apy']}% (Diff: +{ba['apy_diff']}%), Break-even: {ba['break_even_days']} days")
