"""
Tests for FastAPI endpoints and HTML views.
"""

from fastapi.testclient import TestClient
from web.app import app

client = TestClient(app)


def test_dashboard_view():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "DeFi Tier-1" in resp.text


def test_advisor_view():
    resp = client.get("/advisor")
    assert resp.status_code == 200
    assert "AI Советник" in resp.text


def test_api_overview():
    resp = client.get("/api/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_tvl_monitored" in data


def test_api_pools():
    resp = client.get("/api/pools?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


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
