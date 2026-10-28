from datetime import UTC, datetime, timedelta


def register(client, email="analyst@example.com"):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Analyst Trader",
            "email": email,
            "password": "long-enough-password",
        },
    )
    assert response.status_code == 201
    return response.json()


def add_trade(
    client,
    *,
    opened_at: datetime,
    closed_at: datetime,
    outcome: str,
    pnl: float,
    r_multiple: float | None,
    **context,
):
    response = client.post(
        "/api/v1/trades",
        json={
            "symbol": "EURUSD",
            "direction": "Long",
            "strategy": "London breakout",
            "setup": "Opening range",
            "outcome": outcome,
            "pnl": pnl,
            "r_multiple": r_multiple,
            "opened_at": opened_at.isoformat(),
            "closed_at": closed_at.isoformat(),
            **context,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_performance_endpoints_require_authentication(client):
    for endpoint in (
        "/api/v1/performance/edge-snapshot",
        "/api/v1/performance/strategies",
        "/api/v1/performance/behavior",
        "/api/v1/performance/roadmap",
    ):
        assert client.get(endpoint).status_code == 401


def test_edge_snapshot_calculates_r_metrics_and_excursion_coverage(client):
    register(client)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    add_trade(
        client,
        opened_at=start,
        closed_at=start + timedelta(minutes=30),
        outcome="win",
        pnl=200,
        r_multiple=2,
        mae_r=0.25,
        mfe_r=2.5,
    )
    add_trade(
        client,
        opened_at=start + timedelta(days=1),
        closed_at=start + timedelta(days=1, minutes=30),
        outcome="loss",
        pnl=-100,
        r_multiple=-1,
        mae_r=1,
        mfe_r=0.5,
    )

    response = client.get("/api/v1/performance/edge-snapshot")
    assert response.status_code == 200
    metrics = response.json()["metrics"]
    assert metrics["trade_count"] == 2
    assert metrics["expectancy_r"] == 0.5
    assert metrics["profit_factor"] == 2
    assert metrics["average_win_r"] == 2
    assert metrics["average_loss_r"] == -1
    assert metrics["max_drawdown_r"] == 1
    assert metrics["average_mae_r"] == 0.625
    assert metrics["average_mfe_r"] == 1.5
    assert metrics["sample_reliability"] == "insufficient"


def test_behavior_uses_explicit_labels_and_flags_post_loss_timing(client):
    register(client)
    start = datetime(2026, 2, 1, 23, 50, tzinfo=UTC)
    add_trade(
        client,
        opened_at=start,
        closed_at=start + timedelta(minutes=5),
        outcome="loss",
        pnl=-50,
        r_multiple=-1,
        emotional_state="Frustrated",
        rule_breaks=["Moved stop"],
    )
    trade = add_trade(
        client,
        opened_at=start + timedelta(minutes=15),
        closed_at=start + timedelta(minutes=25),
        outcome="win",
        pnl=80,
        r_multiple=1.6,
        emotional_state="Focused",
        confluences=["Trend", "Trend"],
    )
    assert trade["confluences"] == ["Trend"]
    assert trade["setup"] == "Opening range"
    response = client.get("/api/v1/performance/behavior?revenge_window_minutes=30")
    assert response.status_code == 200
    body = response.json()
    assert body["revenge_timing"]["trade_count"] == 1
    assert body["emotional_state"][0]["key"] == "Focused"
    assert body["recorded_rule_breaks"][0]["key"] == "Moved stop"
    assert body["recorded_confluences"][0]["key"] == "Trend"
    assert "not show" in body["interpretation_limit"]
    setups = client.get("/api/v1/performance/setups").json()["setups"]
    assert setups[0]["key"] == "Opening range"
    boundary = client.get(
        "/api/v1/performance/behavior",
        params={
            "start_date": "2026-02-02",
            "end_date": "2026-02-02",
            "revenge_window_minutes": 30,
        },
    )
    assert boundary.status_code == 200
    assert boundary.json()["revenge_timing"]["trade_count"] == 1


def test_user_data_isolation_and_account_scope_validation(client):
    register(client)
    start = datetime(2026, 3, 1, tzinfo=UTC)
    add_trade(
        client,
        opened_at=start,
        closed_at=start + timedelta(minutes=5),
        outcome="win",
        pnl=10,
        r_multiple=1,
    )
    client.post("/api/v1/auth/logout")
    register(client, "second@example.com")
    assert client.get("/api/v1/performance/edge-snapshot").json()["metrics"]["trade_count"] == 0
    assert (
        client.get(
            "/api/v1/performance/edge-snapshot?account_id=00000000-0000-0000-0000-000000000001"
        ).status_code
        == 404
    )


def test_roadmap_snapshot_persists_and_progress_is_user_scoped(client):
    register(client)
    start = datetime(2026, 4, 1, tzinfo=UTC)
    add_trade(
        client,
        opened_at=start,
        closed_at=start + timedelta(minutes=5),
        outcome="loss",
        pnl=-25,
        r_multiple=-1,
    )
    saved = client.post(
        "/api/v1/performance/roadmaps",
        params={"start_date": "2026-04-01", "end_date": "2026-04-30"},
    )
    assert saved.status_code == 201, saved.text
    snapshot = saved.json()
    assert snapshot["trade_count"] == 1
    assert snapshot["progress_status"] == "pending"
    assert snapshot["metrics"]["performance"]["expectancy_r"] == -1

    listing = client.get("/api/v1/performance/roadmaps")
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == snapshot["id"]
    assert listing.json()[0]["start_date"] == "2026-04-01"

    updated = client.patch(
        f"/api/v1/performance/roadmaps/{snapshot['id']}",
        json={"progress_status": "in_progress", "progress_notes": "Testing one rule"},
    )
    assert updated.status_code == 200
    assert updated.json()["progress_status"] == "in_progress"

    client.post("/api/v1/auth/logout")
    register(client, "second@example.com")
    assert client.get("/api/v1/performance/roadmaps").json() == []
    assert (
        client.patch(
            f"/api/v1/performance/roadmaps/{snapshot['id']}",
            json={"progress_status": "completed"},
        ).status_code
        == 404
    )


def test_report_compares_with_prior_period_and_is_user_scoped(client):
    register(client)
    base = datetime(2026, 2, 10, tzinfo=UTC)
    current_trade = add_trade(client, opened_at=base, closed_at=base + timedelta(minutes=5),
                              outcome="win", pnl=100, r_multiple=1)
    earlier = base - timedelta(days=5)
    add_trade(client, opened_at=earlier, closed_at=earlier + timedelta(minutes=5),
              outcome="loss", pnl=-50, r_multiple=-1)
    response = client.get(
        "/api/v1/performance/report",
        params={"start_date": "2026-02-08", "end_date": "2026-02-14", "timezone": "UTC"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current"]["trade_count"] == 1
    assert body["previous"]["trade_count"] == 1
    assert body["scope"]["previous_period"]["start_date"] == "2026-02-01"
    assert body["identity"]["dominant_strategy"] == {
        "name": "London breakout",
        "trade_count": 1,
        "share_pct": 100,
    }
    assert body["identity"]["strongest_observed_strategy"] is None
    assert body["strategies"][0]["evidence"] == [
        {
            "trade_id": current_trade["id"],
            "symbol": "EURUSD",
            "setup": "Opening range",
            "source": "user",
            "outcome": "win",
            "closed_at": current_trade["closed_at"],
        }
    ]
    expectancy = next(c for c in body["comparison"] if c["metric"] == "expectancy_r")
    assert expectancy["change"] == 2
    bad = client.get(
        "/api/v1/performance/report",
        params={"start_date": "2026-02-14", "end_date": "2026-02-08"},
    )
    assert bad.status_code == 422
    client.cookies.clear()
    assert client.get(
        "/api/v1/performance/report",
        params={"start_date": "2026-02-08", "end_date": "2026-02-14"},
    ).status_code == 401


def test_goals_and_experiments_are_user_scoped(client):
    register(client)
    created = client.post(
        "/api/v1/development/goals",
        json={
            "title": "Cut losses",
            "metric": "expectancy_r",
            "direction": "increase",
            "target_value": 0.3,
        },
    )
    assert created.status_code == 201
    goal = created.json()
    assert goal["progress"] is None and goal["current_sample"] == 0

    exp = client.post(
        "/api/v1/development/experiments",
        json={
            "goal_id": goal["id"],
            "title": "No trades after 2 losses",
            "hypothesis": "Fewer revenge trades",
            "rule": "Stop after two losses",
            "start_date": "2024-01-01",
        },
    )
    assert exp.status_code == 201
    assert exp.json()["evidence"]["trade_count"] >= 0
    patched = client.patch(
        f"/api/v1/development/experiments/{exp.json()['id']}",
        json={"status": "concluded", "conclusion": "Kept the rule"},
    )
    assert patched.json()["status"] == "concluded"
    assert (
        client.post(
            "/api/v1/development/goals",
            json={"title": "x", "metric": "bogus", "direction": "increase", "target_value": 1},
        ).status_code
        == 422
    )

    client.cookies.clear()
    register(client, "other@example.com")
    assert client.get("/api/v1/development/goals").json() == []
    assert client.get("/api/v1/development/experiments").json() == []
    foreign = client.patch(f"/api/v1/development/goals/{goal['id']}", json={"status": "paused"})
    assert foreign.status_code == 404
    assert client.delete(f"/api/v1/development/experiments/{exp.json()['id']}").status_code == 404
    assert (
        client.post(
            "/api/v1/development/experiments",
            json={
                "goal_id": goal["id"],
                "title": "t",
                "hypothesis": "h",
                "rule": "r",
                "start_date": "2024-01-01",
            },
        ).status_code
        == 404
    )

    client.cookies.clear()
    assert client.get("/api/v1/development/goals").status_code == 401


def test_equity_history_and_execution_timeline_are_user_scoped(client):
    register(client)
    now = datetime.now(UTC)
    trade = add_trade(
        client,
        opened_at=now - timedelta(hours=2),
        closed_at=now - timedelta(hours=1),
        outcome="win",
        pnl=10,
        r_multiple=1,
    )
    history = client.get("/api/v1/performance/equity-history")
    assert history.status_code == 200
    assert history.json()["series"] == []
    timeline = client.get(f"/api/v1/performance/execution-timeline/{trade['id']}")
    assert timeline.status_code == 200
    assert timeline.json()["has_terminal_data"] is False

    client.cookies.clear()
    register(client, "other2@example.com")
    assert client.get(f"/api/v1/performance/execution-timeline/{trade['id']}").status_code == 404
    client.cookies.clear()
    assert client.get("/api/v1/performance/equity-history").status_code == 401
