"""
Tests for Personal Cabinet (Portfolio Management), Boost positions,
Advanced Math (Supply, Borrow, LP v3, IL, Net PnL), Autocomplete, and Web3 Wallet Scanner.
"""

import os
import tempfile
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from web.app import app
from data.database import (
    init_db, add_portfolio_position, get_user_portfolio,
    get_portfolio_summary, delete_portfolio_position, update_portfolio_position,
    get_distinct_chains, get_distinct_protocols, get_distinct_assets,
    search_pools_for_autocomplete, insert_snapshots
)
from data.wallet_scanner import validate_address, scan_wallet_positions

client = TestClient(app)


@pytest.fixture
def test_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_portfolio.db")
    init_db(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


def test_portfolio_database_crud(test_db):
    # Add position 1: $10,000 at 5% APY
    id1 = add_portfolio_position(
        user_id="user_test",
        protocol="aave-v3",
        chain="Ethereum",
        asset="USDT",
        amount_usd=10000.0,
        current_apy=5.0,
        notes="Safe cold wallet",
        db_path=test_db
    )
    assert id1 > 0

    # Add position 2: $20,000 at 8% APY
    id2 = add_portfolio_position(
        user_id="user_test",
        protocol="morpho-blue",
        chain="Base",
        asset="USDC",
        amount_usd=20000.0,
        current_apy=8.0,
        notes="High yield vault",
        db_path=test_db
    )
    assert id2 > 0

    # Retrieve positions
    positions = get_user_portfolio(user_id="user_test", db_path=test_db)
    assert len(positions) == 2
    assert positions[0]["amount_usd"] == 20000.0
    assert positions[1]["amount_usd"] == 10000.0

    # Calculate summary
    summary = get_portfolio_summary(user_id="user_test", db_path=test_db)
    assert summary["total_capital"] == 30000.0
    assert summary["weighted_apy"] == 7.0
    assert summary["annual_income"] == 2100.0
    assert summary["monthly_income"] == 175.0

    # Update position
    updated = update_portfolio_position(
        pos_id=id1,
        user_id="user_test",
        amount_usd=15000.0,
        current_apy=6.0,
        db_path=test_db
    )
    assert updated is True

    # Delete position 2
    deleted = delete_portfolio_position(pos_id=id2, user_id="user_test", db_path=test_db)
    assert deleted is True

    remaining = get_user_portfolio(user_id="user_test", db_path=test_db)
    assert len(remaining) == 1
    assert remaining[0]["amount_usd"] == 15000.0
    assert remaining[0]["current_apy"] == 6.0


def test_advanced_position_types_and_math(test_db):
    past_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

    # 1. Supply Position with entry_date
    id_supply = add_portfolio_position(
        user_id="adv_user",
        protocol="aave-v3",
        chain="Arbitrum",
        asset="USDC",
        amount_usd=10000.0,
        current_apy=10.0,
        position_type="lending",
        entry_date=past_date,
        db_path=test_db
    )
    assert id_supply > 0

    # 2. Borrow Position with entry_date and accrued debt
    id_borrow = add_portfolio_position(
        user_id="adv_user",
        protocol="spark",
        chain="Ethereum",
        asset="USDT",
        amount_usd=5000.0,
        current_apy=8.0,
        position_type="borrow",
        entry_date=past_date,
        db_path=test_db
    )
    assert id_borrow > 0

    # 3. Liquidity Pool (LP v3) Position: ETH-USDC
    # Entry: 1 ETH @ $2500 + 2500 USDC @ $1.00 = $5000 initial
    # Current: 0.85 ETH @ $3100 ($2635) + 3072.5 USDC @ $1.00 = $5707.50 current LP value
    # HODL: 1 ETH @ $3100 + 2500 USDC = $5600
    # Fees earned: $350
    id_lp = add_portfolio_position(
        user_id="adv_user",
        protocol="uniswap-v3",
        chain="Ethereum",
        asset="ETH-USDC",
        position_type="liquidity_pool",
        entry_date=past_date,
        entry_amount_a=1.0,
        entry_price_a=2500.0,
        entry_amount_b=2500.0,
        entry_price_b=1.0,
        current_amount_a=0.85,
        current_price_a=3100.0,
        current_amount_b=3072.50,
        current_price_b=1.0,
        fee_earnings_usd=350.0,
        current_apy=25.0,
        db_path=test_db
    )
    assert id_lp > 0

    positions = get_user_portfolio(user_id="adv_user", db_path=test_db)
    assert len(positions) == 3

    supply_pos = next(p for p in positions if p["position_type"] == "lending")
    borrow_pos = next(p for p in positions if p["position_type"] == "borrow")
    lp_pos = next(p for p in positions if p["position_type"] == "liquidity_pool")

    # Verify Supply Math
    assert supply_pos["earned_yield_usd"] > 0
    assert supply_pos["earned_yield_tokens"] > 0
    assert supply_pos["net_pnl_usd"] > 0

    # Verify Borrow Math
    assert borrow_pos["borrow_debt_usd"] > 0
    assert borrow_pos["borrow_debt_tokens"] > 0
    assert borrow_pos["net_pnl_usd"] < 0

    # Verify LP Math
    assert lp_pos["initial_value_usd"] == 5000.0
    assert lp_pos["current_value_usd"] == 5707.50
    assert lp_pos["fee_earnings_usd"] == 350.0
    # Net PnL = (5707.50 + 350) - 5000 = 1057.50
    assert lp_pos["net_pnl_usd"] == 1057.50
    assert lp_pos["net_pnl_pct"] > 0

    # Summary
    summary = get_portfolio_summary(user_id="adv_user", db_path=test_db)
    assert summary["positions_count"] == 3
    assert summary["total_supply_usd"] > 0
    assert summary["total_borrow_usd"] > 0
    assert summary["net_capital_usd"] == summary["total_supply_usd"] - summary["total_borrow_usd"]
    assert summary["total_fee_earnings"] == 350.0


def test_zero_division_and_edge_cases(test_db):
    # Position with 0 amount, 0 apy, empty entry_date
    id_zero = add_portfolio_position(
        user_id="zero_user",
        protocol="aave-v3",
        chain="Ethereum",
        asset="USDT",
        amount_usd=0.0,
        current_apy=0.0,
        position_type="lending",
        entry_date=None,
        db_path=test_db
    )
    assert id_zero > 0
    positions = get_user_portfolio(user_id="zero_user", db_path=test_db)
    assert len(positions) == 1
    assert positions[0]["net_pnl_pct"] == 0.0
    assert positions[0]["earned_yield_usd"] == 0.0

    # LP Position with 0 price and 0 amounts
    id_lp_zero = add_portfolio_position(
        user_id="zero_user",
        protocol="uniswap-v3",
        chain="Arbitrum",
        asset="ABC-XYZ",
        position_type="liquidity_pool",
        entry_amount_a=0.0,
        entry_price_a=0.0,
        entry_amount_b=0.0,
        entry_price_b=0.0,
        db_path=test_db
    )
    assert id_lp_zero > 0
    lp_positions = [p for p in get_user_portfolio(user_id="zero_user", db_path=test_db) if p["position_type"] == "liquidity_pool"]
    assert len(lp_positions) == 1
    assert lp_positions[0]["net_pnl_pct"] == 0.0


def test_position_auto_compute_amount(test_db):
    # Lending with token amount and price given, amount_usd = 0
    id_auto = add_portfolio_position(
        user_id="auto_user",
        protocol="aave-v3",
        chain="Ethereum",
        asset="ETH",
        amount_usd=0.0,
        entry_amount_a=2.5,
        entry_price_a=3000.0,
        current_apy=5.0,
        position_type="lending",
        db_path=test_db
    )
    assert id_auto > 0
    pos = get_user_portfolio(user_id="auto_user", db_path=test_db)[0]
    assert pos["amount_usd"] == 7500.0


def test_distinct_autocomplete_helpers(test_db):
    chains = get_distinct_chains(db_path=test_db)
    assert "Ethereum" in chains
    assert "Arbitrum" in chains
    assert "Base" in chains
    assert "Solana" in chains
    assert len(chains) >= 20

    protocols = get_distinct_protocols(db_path=test_db)
    assert "Aave v3" in protocols
    assert "Uniswap v3" in protocols
    assert len(protocols) >= 15

    assets = get_distinct_assets(db_path=test_db)
    assert "USDC" in assets
    assert "USDT" in assets
    assert "ETH" in assets

    # Seed a snapshot to test autocomplete pool search
    insert_snapshots([{
        "pool_id": "test-pool-arb-usdc",
        "project": "aave-v3",
        "chain": "Arbitrum",
        "symbol": "USDC",
        "tvl_usd": 5000000.0,
        "apy": 6.5,
        "apy_base": 6.5,
        "apy_reward": 0.0
    }], db_path=test_db)

    results = search_pools_for_autocomplete(q="usdc", chain="Arbitrum", db_path=test_db)
    assert len(results) >= 1
    assert results[0]["project"] == "aave-v3"
    assert results[0]["apy"] == 6.5


def test_wallet_scanner():
    # Address validation
    assert validate_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")["valid"] is True
    assert validate_address("0xInvalid")["valid"] is False
    assert validate_address("9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin")["valid"] is True # Solana format

    # EVM scanning
    res = scan_wallet_positions(
        address="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        chains=["Ethereum", "Arbitrum", "Base"]
    )
    assert res["status"] == "success"
    assert len(res["positions"]) >= 3
    assert any(p["position_type"] == "lending" for p in res["positions"])
    assert any(p["position_type"] == "borrow" for p in res["positions"])
    assert any(p["position_type"] == "liquidity_pool" for p in res["positions"])
    assert res["total_value_usd"] > 0
    assert "scanned_chains" in res


def test_multichain_wallet_scanner_rich_data():
    all_chains = ["Ethereum", "Arbitrum", "Base", "Optimism", "Polygon", "BSC", "Avalanche", "Sonic", "Solana", "Sui"]
    res = scan_wallet_positions(
        address="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        chains=all_chains
    )
    assert res["status"] == "success"
    assert len(res["positions"]) >= 10
    assert "chain_summaries" in res
    assert len(res["chain_summaries"]) >= 8
    assert "overall_summary" in res
    assert res["overall_summary"]["total_deposited_usd"] > 0
    assert res["overall_summary"]["current_value_usd"] > 0
    assert res["overall_summary"]["chains_count"] >= 8

    # Check that each position has initial deposit and Russian formatted date
    for p in res["positions"]:
        assert "initial_deposit_usd" in p
        assert p["initial_deposit_usd"] > 0
        assert "deposit_date_display" in p
        assert "назад" in p["deposit_date_display"] or "сегодня" in p["deposit_date_display"]
        assert "current_value_usd" in p
        assert "net_pnl_usd" in p
        assert "net_pnl_pct" in p

    # Test single-chain scanning gives lending, borrow and LP
    single_res = scan_wallet_positions(
        address="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        chains=["Arbitrum"]
    )
    assert single_res["status"] == "success"
    assert any(p["position_type"] == "lending" for p in single_res["positions"])
    assert any(p["position_type"] == "borrow" for p in single_res["positions"])
    assert any(p["position_type"] == "liquidity_pool" for p in single_res["positions"])


def test_portfolio_web_endpoints():
    # Test HTML view with boost trigger
    resp = client.get("/portfolio?boost=1")
    assert resp.status_code == 200
    assert "Мой Портфель" in resp.text
    assert "Swiss" not in resp.text # Clean html
    assert "Boost" in resp.text

    # Test Autocomplete Options API
    opt_resp = client.get("/api/portfolio/options")
    assert opt_resp.status_code == 200
    opt_data = opt_resp.json()
    assert "chains" in opt_data
    assert "protocols" in opt_data
    assert "assets" in opt_data
    assert len(opt_data["chains"]) >= 20

    # Test Search Pools API
    search_resp = client.get("/api/portfolio/search-pools?q=usd")
    assert search_resp.status_code == 200
    assert isinstance(search_resp.json(), list)

    # Test API add LP position
    lp_payload = {
        "protocol": "uniswap-v3",
        "chain": "Arbitrum",
        "asset": "ETH-USDC",
        "position_type": "liquidity_pool",
        "entry_date": "2024-11-01",
        "entry_amount_a": 1.0,
        "entry_price_a": 2500.0,
        "entry_amount_b": 2500.0,
        "entry_price_b": 1.0,
        "current_amount_a": 0.9,
        "current_price_a": 3000.0,
        "current_amount_b": 2800.0,
        "current_price_b": 1.0,
        "fee_earnings_usd": 220.0,
        "current_apy": 22.0,
        "user_id": "test_web_user_v2"
    }
    add_resp = client.post("/api/portfolio/position", json=lp_payload)
    assert add_resp.status_code == 200
    add_data = add_resp.json()
    assert add_data["status"] == "success"
    pos_id = add_data["id"]

    # Test PUT update position
    update_payload = {
        "protocol": "uniswap-v3",
        "chain": "Arbitrum",
        "asset": "ETH-USDC",
        "position_type": "liquidity_pool",
        "fee_earnings_usd": 300.0,
        "current_apy": 24.0,
        "user_id": "test_web_user_v2"
    }
    put_resp = client.put(f"/api/portfolio/position/{pos_id}", json=update_payload)
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["status"] == "success"

    # Test Wallet Scan & Import
    scan_resp = client.post("/api/portfolio/wallet-scan", json={
        "address": "0x1111111254fb6c44bac0bed2854e76f90643097d",
        "chains": ["Ethereum", "Base"]
    })
    assert scan_resp.status_code == 200
    scan_data = scan_resp.json()
    assert scan_data["status"] == "success"
    assert len(scan_data["positions"]) > 0

    import_resp = client.post("/api/portfolio/wallet-import", json={
        "user_id": "test_web_user_v2",
        "positions": scan_data["positions"]
    })
    assert import_resp.status_code == 200
    import_data = import_resp.json()
    assert import_data["status"] == "success"
    assert import_data["imported_count"] == len(scan_data["positions"])

    # Test delete
    del_resp = client.delete(f"/api/portfolio/position/{pos_id}?user_id=test_web_user_v2")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "success"


def test_user_wallet_scan_matches_debank():
    """Verify scanning 0xdBbbB030ec24d3B075BFb74637B3D70DE0e620b3 accurately matches DeBank on-chain state."""
    from data.wallet_scanner import scan_wallet_positions, DASHBOARD_CHAINS

    target_address = "0xdBbbB030ec24d3B075BFb74637B3D70DE0e620b3"
    res = scan_wallet_positions(target_address, chains=DASHBOARD_CHAINS)

    assert res["status"] == "success"
    assert res["total_chains_count"] == 28
    assert len(res["scanned_chains"]) == 28

    # 1. 0 active protocol positions ($0.00 in Lending / LP)
    assert res["protocol_positions"] == []
    assert res["has_protocol_positions"] is False

    # 2. Real wallet tokens total value ~$2.75 (range 2.0 to 4.0 depending on live prices)
    assert 2.0 <= res["total_value_usd"] <= 4.0

    # 3. Chains with balances: Avalanche (AVAX), Arbitrum (ETH), Plasma (XPL & USDT0), Base (ETH)
    token_chains = {t["chain"] for t in res["wallet_tokens"]}
    assert "Avalanche" in token_chains
    assert "Arbitrum" in token_chains
    assert "Plasma" in token_chains
    assert "Base" in token_chains

    # 4. Plasma USDT0 token detected
    usdt0_tokens = [t for t in res["wallet_tokens"] if t["symbol"] == "USDT0"]
    assert len(usdt0_tokens) == 1
    assert usdt0_tokens[0]["balance"] == 0.01

    # 5. Recent on-chain transactions detected
    assert len(res["recent_transactions"]) > 0
    assert any(tx["chain"] == "Plasma" or "0x1e79" in tx.get("to", "") for tx in res["recent_transactions"])


def test_polygon_hyperliquid_scan_matches_debank():
    """Verify scanning 0xb8ce59fc3717ada4c02eadf9682a9e934f625ebb matches DeBank (~$37,000 net worth with POL at ~$0.095)."""
    from data.wallet_scanner import scan_wallet_positions, DASHBOARD_CHAINS

    target_address = "0xb8ce59fc3717ada4c02eadf9682a9e934f625ebb"
    res = scan_wallet_positions(target_address, chains=DASHBOARD_CHAINS)

    assert res["status"] == "success"
    # Valuation should be between $30,000 and $45,000 (not $170,000)
    assert 30000.0 <= res["total_value_usd"] <= 45000.0

    # Verify POL token on Polygon
    pol_tokens = [t for t in res["wallet_tokens"] if t["chain"] == "Polygon" and t["symbol"] == "POL"]
    assert len(pol_tokens) == 1
    assert pol_tokens[0]["balance"] > 370000.0
    assert 0.05 <= pol_tokens[0]["price_usd"] <= 0.15

    # Verify Hyperliquid L1 balance
    hl_tokens = [t for t in res["wallet_tokens"] if t["chain"] == "Hyperliquid L1"]
    assert len(hl_tokens) >= 1
    assert any(t["symbol"] == "USDT0" and t["balance"] > 700.0 for t in hl_tokens)


def test_curated_wallets_database(test_db):
    """Verify curated wallets database operations, seed wallets, and CRUD."""
    from data.database import (
        get_curated_wallets, get_curated_wallet_by_address,
        add_curated_wallet, delete_curated_wallet, update_curated_wallet_ai
    )

    wallets = get_curated_wallets(db_path=test_db)
    assert len(wallets) >= 3

    # Verify user's Revert LP Whale wallet is in seed
    revert_wallet = next((w for w in wallets if "0x47d06a6d5e3f4e738dea3e8df98a4525499f7619" in w["address"].lower()), None)
    assert revert_wallet is not None
    assert "revert.finance" in revert_wallet["revert_url"]
    assert "debank.com" in revert_wallet["debank_url"]
    assert len(revert_wallet["ai_summary"]) > 20

    # Add custom curated wallet
    new_id = add_curated_wallet(
        address="0x28c6c06298d514db089934071355e5743bf21d60",
        label="Binance Hot Wallet 14",
        strategy_type="Exchange Liquidity Hub",
        chains="Ethereum, BSC",
        protocols="Uniswap, PancakeSwap",
        ai_summary="Тестовый аудит стратегии",
        estimated_tvl="$50M+",
        db_path=test_db
    )
    assert new_id > 0

    fetched = get_curated_wallet_by_address("0x28c6c06298d514db089934071355e5743bf21d60", db_path=test_db)
    assert fetched is not None
    assert fetched["label"] == "Binance Hot Wallet 14"

    # Update AI summary
    updated = update_curated_wallet_ai(new_id, "Обновленное резюме от нейросети", db_path=test_db)
    assert updated is True
    updated_fetched = get_curated_wallet_by_address("0x28c6c06298d514db089934071355e5743bf21d60", db_path=test_db)
    assert updated_fetched["ai_summary"] == "Обновленное резюме от нейросети"

    # Delete
    deleted = delete_curated_wallet(new_id, db_path=test_db)
    assert deleted is True
    assert get_curated_wallet_by_address("0x28c6c06298d514db089934071355e5743bf21d60", db_path=test_db) is None


def test_curated_wallets_api():
    """Verify REST API endpoints for curated wallets."""
    # 1. GET /api/curated-wallets
    resp = client.get("/api/curated-wallets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["count"] >= 3
    assert any("0x47d06a6d5e3f4e738dea3e8df98a4525499f7619" in w["address"].lower() for w in data["wallets"])

    # 2. POST /api/curated-wallets (add wallet with AI generation)
    test_addr = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # USDC contract as dummy EVM address
    add_resp = client.post("/api/curated-wallets", json={
        "address": test_addr,
        "label": "USDC Treasury Whale",
        "strategy_type": "Stablecoin Collateral",
        "chains": "Ethereum",
        "protocols": "Aave v3, MakerDAO",
        "generate_ai": True
    })
    assert add_resp.status_code == 200
    add_data = add_resp.json()
    assert add_data["status"] == "success"
    wallet_id = add_data["id"]
    assert wallet_id > 0
    assert len(add_data["wallet"]["ai_summary"]) > 10

    # 3. POST /api/curated-wallets/{id}/refresh-ai
    refresh_resp = client.post(f"/api/curated-wallets/{wallet_id}/refresh-ai")
    assert refresh_resp.status_code == 200
    refresh_data = refresh_resp.json()
    assert refresh_data["status"] == "success"
    assert len(refresh_data["wallet"]["ai_summary"]) > 10

    # 4. DELETE /api/curated-wallets/{id}
    del_resp = client.delete(f"/api/curated-wallets/{wallet_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "success"


def test_portfolio_page_contains_curated_wallets_and_debank_elements():
    """Verify the /portfolio page renders DeBank elements and Curated Wallets modal."""
    resp = client.get("/portfolio")
    assert resp.status_code == 200
    html = resp.text

    # Must contain Curated Wallets button and modal
    assert "Интересные кошельки" in html
    assert "curatedWalletsModal" in html
    assert "0x47d06a6d5e3f4e738dea3e8df98a4525499f7619" in html
    assert "revert.finance" in html
    assert "debank.com" in html

    # Must contain auto-chain detection logic
    assert "onWalletAddressInput" in html
    assert "ecosystemDetectBadge" in html
    assert "debank-chain-pill" in html
    assert "filterScanChain" in html



