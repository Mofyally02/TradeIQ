from datetime import datetime, timedelta, timezone


def test_trade_422_variants(client):
    email = "tmp-422@example.com"
    password = "long-enough-password"
    register = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Trader", "email": email, "password": password},
    )
    if register.status_code not in (200, 201):
        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code in (200, 204), login.text

    plan_response = client.post(
        "/api/v1/plans",
        json={
            "symbol": "XAUUSD",
            "direction": "Short",
            "strategy": "London breakout",
            "thesis": "Temporary 422 reproduction",
        },
    )
    print("PLAN", plan_response.status_code, plan_response.text)
    assert plan_response.status_code in (200, 201), plan_response.text
    plan = plan_response.json()

    base = {
        "plan_id": plan["id"], "symbol": "XAUUSD", "direction": "Short",
        "strategy": plan["strategy"], "outcome": "win", "pnl": 3595.8,
        "r_multiple": 2, "entry_price": 3985.03, "exit_price": 4040.79,
        "size": 0.3, "notes": "x", "mae_r": None, "mfe_r": None,
        "emotional_state": None, "confluences": [], "rule_breaks": [],
        "stop_loss": 4040.79, "take_profit": 3869, "opened_at": plan["created_at"],
    }
    now = datetime.now(timezone.utc)
    for label, closed_at in (("NOW", now), ("YESTERDAY", now - timedelta(days=1))):
        response = client.post(
            "/api/v1/trades",
            json={**base, "closed_at": closed_at.isoformat().replace("+00:00", "Z")},
        )
        print(label, response.status_code, response.text)
