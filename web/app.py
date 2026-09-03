"""
Web Dashboard Application (FastAPI).
Serves high-performance UI and JSON APIs for DeFi Yield & Rebalance Dashboard.
"""

import os
import sys
from typing import Optional, List
from fastapi import FastAPI, Request, Query, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from data.database import (
    init_db, get_pool_history, get_pool_by_id,
    get_user_portfolio, add_portfolio_position,
    update_portfolio_position, delete_portfolio_position, get_portfolio_summary
)
from data.metrics_engine import get_enriched_pools, get_market_overview, calculate_pool_metrics
from data.snapshot_worker import fetch_and_store_snapshots
from advisor.rebalance_advisor import evaluate_rebalance
from ai_handler import generate_rebalance_advice, generate_portfolio_advice
from defi_engine import get_category, get_protocol_url, normalize_stable_symbol

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

import threading
import time
import schedule
from contextlib import asynccontextmanager
from data.snapshot_worker import bootstrap_top_pools_history
from data.rollup_worker import run_rollup_job

def _background_scheduler():
    schedule.every(15).minutes.do(fetch_and_store_snapshots)
    schedule.every().day.at("03:00").do(run_rollup_job)
    while True:
        schedule.run_pending()
        time.sleep(30)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    
    # Check if we have snapshots; if empty, bootstrap initial data
    from data.database import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM snapshots")
    row = cur.fetchone()
    count = row["cnt"] if row else 0
    conn.close()

    if count == 0:
        print("[App Startup] DB is empty. Running initial snapshot and bootstrapping history...")
        threading.Thread(target=lambda: (fetch_and_store_snapshots(), bootstrap_top_pools_history(top_n=10)), daemon=True).start()

    # Start background scheduler thread
    scheduler_thread = threading.Thread(target=_background_scheduler, daemon=True)
    scheduler_thread.start()
    print("[App Startup] Background 15-minute snapshot scheduler started.")

    # Start Telegram Bot if token provided and not explicitly disabled
    tg_token = os.getenv("TELEGRAM_TOKEN")
    if tg_token and os.getenv("DISABLE_BOT", "false").lower() != "true":
        try:
            from bot import bot
            def _run_bot():
                print("[App Startup] Starting Telegram Bot polling...")
                bot.infinity_polling(timeout=60, long_polling_timeout=60)
            bot_thread = threading.Thread(target=_run_bot, daemon=True)
            bot_thread.start()
            print("[App Startup] Telegram Bot thread active.")
        except Exception as e:
            print(f"[App Startup] Telegram bot init warning: {e}")

    yield

app = FastAPI(
    title="DeFi Tier-1 Yield & Rebalance Dashboard",
    description="Real-time on-chain analytics and AI portfolio rebalancing for top DeFi protocols",
    version="2.0.0",
    lifespan=lifespan
)

# Mount static and templates
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ──────────────────────────────────────────────
#  HTML VIEW ROUTES
# ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def view_dashboard(request: Request, tab: str = Query("all")):
    is_stables = (tab == "stables")
    active_tab = "stables" if is_stables else "all"
    overview = get_market_overview(stables_only=is_stables)
    pools = get_enriched_pools(stables_only=is_stables, min_tvl=100_000, limit=60)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "overview": overview,
            "pools": pools,
            "active_tab": active_tab,
            "stables_only": is_stables
        }
    )


@app.get("/stables", response_class=HTMLResponse)
async def view_stables(request: Request):
    overview = get_market_overview(stables_only=True)
    pools = get_enriched_pools(stables_only=True, min_tvl=100_000, limit=60)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "overview": overview,
            "pools": pools,
            "active_tab": "stables",
            "stables_only": True
        }
    )


@app.get("/advisor", response_class=HTMLResponse)
async def view_advisor(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="advisor.html",
        context={
            "active_tab": "advisor"
        }
    )


@app.get("/pool/{pool_id}", response_class=HTMLResponse)
async def view_pool_detail(request: Request, pool_id: str):
    metrics = calculate_pool_metrics(pool_id)
    if not metrics:
        return HTMLResponse("<h1>Pool not found</h1>", status_code=404)
    if "category" not in metrics:
        metrics["category"] = get_category(metrics["project"], metrics["symbol"])
    if "protocol_url" not in metrics:
        metrics["protocol_url"] = get_protocol_url(metrics["project"], metrics["pool_id"])
    if "clean_symbol" not in metrics:
        metrics["clean_symbol"] = normalize_stable_symbol(metrics["symbol"])
    if "is_canonical" not in metrics:
        metrics["is_canonical"] = metrics["symbol"].upper() in {"USDC", "USDT", "DAI", "USDS", "USDE", "PYUSD", "GHO", "FRAX", "FDUSD", "CRVUSD"}
    return templates.TemplateResponse(
        request=request,
        name="pool_detail.html",
        context={
            "pool": metrics,
            "active_tab": "dashboard"
        }
    )


@app.get("/api/pool/{pool_id}")
async def api_pool_detail(pool_id: str):
    metrics = calculate_pool_metrics(pool_id)
    if not metrics:
        return JSONResponse({"error": "Pool not found"}, status_code=404)
    if "category" not in metrics:
        metrics["category"] = get_category(metrics["project"], metrics["symbol"])
    if "protocol_url" not in metrics:
        metrics["protocol_url"] = get_protocol_url(metrics["project"], metrics["pool_id"])
    if "clean_symbol" not in metrics:
        metrics["clean_symbol"] = normalize_stable_symbol(metrics["symbol"])
    if "is_canonical" not in metrics:
        metrics["is_canonical"] = metrics["symbol"].upper() in {"USDC", "USDT", "DAI", "USDS", "USDE", "PYUSD", "GHO", "FRAX", "FDUSD", "CRVUSD"}
    return metrics


@app.get("/portfolio", response_class=HTMLResponse)
async def view_portfolio(request: Request):
    summary = get_portfolio_summary()
    positions = get_user_portfolio()
    return templates.TemplateResponse(
        request=request,
        name="portfolio.html",
        context={
            "summary": summary,
            "positions": positions,
            "active_tab": "portfolio"
        }
    )


# ──────────────────────────────────────────────
#  REST JSON API ROUTES
# ──────────────────────────────────────────────

@app.get("/api/overview")
async def api_overview(stables_only: bool = Query(False)):
    return get_market_overview(stables_only=stables_only)


@app.get("/api/pools")
async def api_pools(
    asset: Optional[str] = Query(None),
    chain: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    protocol: Optional[str] = Query(None),
    stables_only: bool = Query(False),
    min_tvl: float = Query(100_000),
    sort_by: str = Query("apy"),
    sort_order: str = Query("desc"),
    limit: int = Query(70)
):
    assets_list = [a.strip().upper() for a in asset.split(",") if a.strip()] if asset else None
    chains_list = [c.strip() for c in chain.split(",") if c.strip()] if chain else None
    protocols_list = [p.strip().lower() for p in protocol.split(",") if p.strip()] if protocol else None

    pools = get_enriched_pools(
        assets=assets_list,
        chains=chains_list,
        protocols=protocols_list,
        category=category,
        stables_only=stables_only,
        min_tvl=min_tvl,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit
    )
    return pools


import requests

_chart_api_cache = {}

@app.get("/api/pool/{pool_id}/history")
async def api_pool_history(pool_id: str, days: int = Query(30)):
    """
    Retrieve historical data points for a specific pool supporting 1w (7d), 1m (30d), 6m (180d), 1y (365d).
    Uses local SQLite snapshots and falls back to DefiLlama chart API on-demand with caching.
    """
    local_history = get_pool_history(pool_id, days=days)

    points = []
    if len(local_history) >= min(12, days):
        points = local_history
    else:
        now = time.time()
        cached = _chart_api_cache.get(pool_id)
        if cached and (now - cached["ts"]) < 1800:
            raw_chart = cached["data"]
        else:
            try:
                r = requests.get(f"https://yields.llama.fi/chart/{pool_id}", timeout=6)
                if r.status_code == 200:
                    raw_chart = r.json().get("data", [])
                    _chart_api_cache[pool_id] = {"data": raw_chart, "ts": now}
                else:
                    raw_chart = []
            except Exception:
                raw_chart = []

        if raw_chart:
            slice_data = raw_chart[-days:] if len(raw_chart) > days else raw_chart
            for pt in slice_data:
                points.append({
                    "timestamp": pt.get("timestamp"),
                    "tvl_usd": pt.get("tvlUsd") or 0.0,
                    "apy": round(float(pt.get("apy") or 0.0), 2),
                    "apy_base": round(float(pt.get("apyBase") or 0.0), 2),
                    "apy_reward": round(float(pt.get("apyReward") or 0.0), 2),
                    "type": "chart_api"
                })
        else:
            points = local_history

    valid_apys = [p["apy"] for p in points if p.get("apy") is not None and p["apy"] >= 0]
    avg_apy = round(sum(valid_apys) / len(valid_apys), 2) if valid_apys else 0.0
    cur_apy = round(points[-1]["apy"], 2) if points else 0.0

    return {
        "points": points,
        "avg_apy": avg_apy,
        "cur_apy": cur_apy,
        "days": days,
        "count": len(points)
    }


class RebalanceRequest(BaseModel):
    asset: str = "USDT"
    amount_usd: float = 10000.0
    current_protocol: str = "aave-v3"
    current_chain: str = "Ethereum"
    current_apy: Optional[float] = None
    category: str = "lending"


@app.post("/api/rebalance")
async def api_rebalance(req: RebalanceRequest):
    eval_res = evaluate_rebalance(
        asset=req.asset,
        amount_usd=req.amount_usd,
        current_protocol=req.current_protocol,
        current_chain=req.current_chain,
        current_apy=req.current_apy,
        category=req.category
    )
    ai_advice = generate_rebalance_advice(eval_res)
    return {
        "evaluation": eval_res,
        "ai_advice": ai_advice
    }


@app.post("/api/snapshot/refresh")
async def api_refresh_snapshots():
    try:
        records = await asyncio.to_thread(fetch_and_store_snapshots)
        return {"status": "success", "count": len(records), "message": f"Successfully updated {len(records)} on-chain snapshots"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ──────────────────────────────────────────────
#  PORTFOLIO (ЛИЧНЫЙ КАБИНЕТ) API
# ──────────────────────────────────────────────

class PortfolioPositionRequest(BaseModel):
    protocol: str
    chain: str
    asset: str
    amount_usd: float
    current_apy: float = 0.0
    pool_id: Optional[str] = None
    notes: Optional[str] = None
    user_id: str = "default_user"


@app.get("/api/portfolio")
async def api_get_portfolio(user_id: str = Query("default_user")):
    summary = get_portfolio_summary(user_id=user_id)
    positions = get_user_portfolio(user_id=user_id)
    return {
        "summary": summary,
        "positions": positions
    }


@app.post("/api/portfolio/position")
async def api_add_portfolio_position(pos: PortfolioPositionRequest):
    new_id = add_portfolio_position(
        user_id=pos.user_id,
        protocol=pos.protocol,
        chain=pos.chain,
        asset=pos.asset,
        amount_usd=pos.amount_usd,
        current_apy=pos.current_apy,
        pool_id=pos.pool_id,
        notes=pos.notes
    )
    summary = get_portfolio_summary(user_id=pos.user_id)
    positions = get_user_portfolio(user_id=pos.user_id)
    return {
        "status": "success",
        "id": new_id,
        "summary": summary,
        "positions": positions
    }


@app.delete("/api/portfolio/position/{pos_id}")
async def api_delete_portfolio_position(pos_id: int, user_id: str = Query("default_user")):
    deleted = delete_portfolio_position(pos_id=pos_id, user_id=user_id)
    summary = get_portfolio_summary(user_id=user_id)
    positions = get_user_portfolio(user_id=user_id)
    return {
        "status": "success" if deleted else "not_found",
        "deleted": pos_id if deleted else None,
        "summary": summary,
        "positions": positions
    }


@app.post("/api/portfolio/evaluate")
async def api_evaluate_portfolio(user_id: str = Query("default_user")):
    summary = get_portfolio_summary(user_id=user_id)
    positions = get_user_portfolio(user_id=user_id)
    overview = get_market_overview(stables_only=False)
    advice = generate_portfolio_advice(summary=summary, positions=positions, market_overview=overview)
    return {
        "summary": summary,
        "positions": positions,
        "ai_advice": advice
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
