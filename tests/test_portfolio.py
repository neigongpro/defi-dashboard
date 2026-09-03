"""
Tests for Personal Cabinet (Portfolio Management), SQLite persistence, and AI advisor integration.
"""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from web.app import app
from data.database import (
    init_db, add_portfolio_position, get_user_portfolio,
    get_portfolio_summary, delete_portfolio_position, update_portfolio_position
)

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
    # Ordered by amount_usd DESC
    assert positions[0]["amount_usd"] == 20000.0
    assert positions[1]["amount_usd"] == 10000.0

    # Calculate summary
    summary = get_portfolio_summary(user_id="user_test", db_path=test_db)
    assert summary["total_capital"] == 30000.0
    # Weighted APY: (10000*5 + 20000*8)/30000 = (50000 + 160000)/30000 = 210000/30000 = 7.0%
    assert summary["weighted_apy"] == 7.0
    # Annual: 30000 * 0.07 = 2100
    assert summary["annual_income"] == 2100.0
    # Monthly: 2100 / 12 = 175
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


def test_portfolio_web_endpoints():
    # Test HTML view
    resp = client.get("/portfolio")
    assert resp.status_code == 200
    assert "Мой Портфель" in resp.text
    assert "Личный Кабинет" in resp.text

    # Test API add position
    payload = {
        "protocol": "spark",
        "chain": "Ethereum",
        "asset": "DAI",
        "amount_usd": 5000.0,
        "current_apy": 6.5,
        "notes": "Test pos API",
        "user_id": "test_web_user"
    }
    add_resp = client.post("/api/portfolio/position", json=payload)
    assert add_resp.status_code == 200
    add_data = add_resp.json()
    assert add_data["status"] == "success"
    assert "id" in add_data
    assert add_data["summary"]["total_capital"] >= 5000.0

    pos_id = add_data["id"]

    # Test API get portfolio
    get_resp = client.get("/api/portfolio?user_id=test_web_user")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert len(get_data["positions"]) >= 1

    # Test AI evaluation endpoint
    eval_resp = client.post("/api/portfolio/evaluate?user_id=test_web_user")
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert "summary" in eval_data
    assert "ai_advice" in eval_data
    assert len(eval_data["ai_advice"]) > 20

    # Test API delete position
    del_resp = client.delete(f"/api/portfolio/position/{pos_id}?user_id=test_web_user")
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["status"] == "success"
