import random
from datetime import UTC, datetime, timedelta

from tests.test_performance import add_trade, register


def seed(client, count=150, revenge_bias=True):
    """Trades opened soon after a loss are strongly negative; the rest have positive expectancy."""
    rng = random.Random(5)
    start = datetime(2026, 1, 5, 9, tzinfo=UTC)
    previous_loss_close = None
    for i in range(count):
        opened = start + timedelta(days=i // 3, hours=(i % 3) * 3)
        quick = revenge_bias and previous_loss_close is not None and i % 2 == 0
        if quick:
            opened = previous_loss_close + timedelta(minutes=10)
        r = rng.choice([-1.8, -1.4, -1.0]) if quick else rng.choice([2.5, 2.0, 2.5, -1.0, -1.0, -1.0])
        closed = opened + timedelta(minutes=40)
        add_trade(
            client,
            opened_at=opened,
            closed_at=closed,
            outcome="win" if r > 0 else "loss",
            pnl=r * 100,
            r_multiple=r,
            mfe_r=abs(r) + 0.2 if r > 0 else 0.3,
        )
        previous_loss_close = closed if r < 0 else None


def test_agent_requires_authentication(client):
    assert client.post("/api/v1/agent/run").status_code == 401


def test_agent_reports_readiness_without_insights_on_small_samples(client):
    register(client)
    seed(client, count=6, revenge_bias=False)
    body = client.post("/api/v1/agent/run").json()
    assert body["insights"] == []
    assert body["readiness"]["ready"] is False
    assert body["readiness"]["tips"]
    assert body["core"]["sqn"] is None
    assert body["core"]["win_rate_ci_pct"] is not None


def test_agent_flags_revenge_trading_and_persists_workflow_state(client):
    register(client)
    seed(client)
    first = client.post("/api/v1/agent/run").json()
    codes = {item["code"] for item in first["insights"]}
    assert "REVENGE_TRADING" in codes
    revenge = next(item for item in first["insights"] if item["code"] == "REVENGE_TRADING")
    assert revenge["effect_size"] < 0 and revenge["q_value"] <= 0.2
    assert revenge["evidence"]["trade_ids"] and revenge["recommended_action"]
    assert first["process"]["weekly"]

    patched = client.patch(
        f"/api/v1/agent/insights/{revenge['id']}", json={"status": "accepted", "feedback": "useful"}
    )
    assert patched.status_code == 200
    again = client.post("/api/v1/agent/run").json()
    kept = next(item for item in again["insights"] if item["id"] == revenge["id"])
    assert kept["status"] == "accepted" and kept["feedback"] == "useful"
    assert client.patch(f"/api/v1/agent/insights/{revenge['id']}", json={}).status_code == 422


def test_agent_insights_are_private_per_user(client):
    register(client, "owner@example.com")
    seed(client)
    insight_id = client.post("/api/v1/agent/run").json()["insights"][0]["id"]
    client.post("/api/v1/auth/logout")
    register(client, "other@example.com")
    response = client.patch(f"/api/v1/agent/insights/{insight_id}", json={"status": "seen"})
    assert response.status_code == 404
    assert client.post("/api/v1/agent/run").json()["insights"] == []
