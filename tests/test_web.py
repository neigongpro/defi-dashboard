"""
Tests for FastAPI endpoints and HTML views.
"""

from fastapi.testclient import TestClient
from web.app import app

client = TestClient(app)


def test_dashboard_view():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "DeFi" in resp.text


def test_stables_view():
    resp = client.get("/stables")
    assert resp.status_code == 200
    assert "Стейблкоин" in resp.text or "USDC" in resp.text


def test_advisor_view():
    resp = client.get("/advisor")
    assert resp.status_code == 200
    assert "AI" in resp.text


def test_api_overview():
    resp = client.get("/api/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_tvl_monitored" in data


def test_api_overview_stables():
    resp = client.get("/api/overview?stables_only=true")
    assert resp.status_code == 200
    data = resp.json()
    assert "avg_stable_apy" in data


def test_api_pools():
    resp = client.get("/api/pools?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_api_pools_categories():
    # Lending should not contain pair symbols
    resp = client.get("/api/pools?category=lending&limit=20")
    assert resp.status_code == 200
    data = resp.json()
    for p in data:
        assert "-" not in p["symbol"]
        assert "/" not in p["symbol"]


def test_api_pools_sorting_and_tvl():
    # Test sort_order and min_tvl
    resp = client.get("/api/pools?sort_by=tvl&sort_order=asc&min_tvl=100000&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if len(data) >= 2:
        assert data[0]["tvl_usd"] <= data[1]["tvl_usd"]

    # Test sorting by project alphabetically
    resp_proj = client.get("/api/pools?sort_by=project&sort_order=asc&limit=5")
    assert resp_proj.status_code == 200
    data_proj = resp_proj.json()
    if len(data_proj) >= 2:
        assert data_proj[0]["project"].lower() <= data_proj[1]["project"].lower()


def test_api_rebalance_endpoint():
    payload = {
        "asset": "USDT",
        "amount_usd": 10000.0,
        "current_protocol": "aave-v3",
        "current_chain": "Ethereum",
        "current_apy": 4.0,
        "category": "lending"
    }
    resp = client.post("/api/rebalance", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "evaluation" in data
    assert "ai_advice" in data


def test_api_pool_history():
    pools_resp = client.get("/api/pools?limit=1")
    assert pools_resp.status_code == 200
    pools = pools_resp.json()
    if pools:
        pid = pools[0]["pool_id"]
        # Test 1w (7 days)
        h7_resp = client.get(f"/api/pool/{pid}/history?days=7")
        assert h7_resp.status_code == 200
        h7 = h7_resp.json()
        assert "points" in h7
        assert "avg_apy" in h7
        assert h7["days"] == 7

        # Test 1m (30 days)
        h30_resp = client.get(f"/api/pool/{pid}/history?days=30")
        assert h30_resp.status_code == 200
        h30 = h30_resp.json()
        assert "points" in h30
        assert h30["days"] == 30


def test_pool_detail_view_and_api():
    pools_resp = client.get("/api/pools?limit=1")
    assert pools_resp.status_code == 200
    pools = pools_resp.json()
    if pools:
        pid = pools[0]["pool_id"]
        # Test HTML view
        detail_resp = client.get(f"/pool/{pid}")
        assert detail_resp.status_code == 200
        assert "Назад к таблице" in detail_resp.text

        # Test API JSON endpoint
        api_resp = client.get(f"/api/pool/{pid}")
        assert api_resp.status_code == 200
        data = api_resp.json()
        assert data["pool_id"] == pid
        assert "category" in data
        assert "stability_score" in data
        assert "clean_symbol" in data


def test_pool_not_found():
    resp = client.get("/pool/non-existent-pool-id-12345")
    assert resp.status_code == 404

    api_resp = client.get("/api/pool/non-existent-pool-id-12345")
    assert api_resp.status_code == 404


def test_portfolio_flow():
    # HTML view
    resp = client.get("/portfolio")
    assert resp.status_code == 200
    assert "Портфель" in resp.text

    # List positions
    list_resp = client.get("/api/portfolio")
    assert list_resp.status_code == 200
    pdata = list_resp.json()
    assert "positions" in pdata
    assert "summary" in pdata

    # Add position
    add_payload = {
        "asset": "USDC",
        "protocol": "aave-v3",
        "chain": "Arbitrum",
        "amount_usd": 5000.0,
        "entry_apy": 6.5,
        "current_apy": 6.5,
        "category": "lending",
        "notes": "Test position"
    }
    create_resp = client.post("/api/portfolio/position", json=add_payload)
    assert create_resp.status_code == 200
    pos = create_resp.json()
    assert "id" in pos
    pos_id = pos["id"]

    # Delete position
    del_resp = client.delete(f"/api/portfolio/position/{pos_id}")
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data.get("deleted") == pos_id
