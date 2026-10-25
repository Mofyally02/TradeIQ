from datetime import UTC, datetime, timedelta


def register(client, email="trader@example.com"):
    response = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Trader", "email": email, "password": "long-enough-password"},
    )
    assert response.status_code == 201
    return response.json()


def make_account(client, name="Primary"):
    response = client.post(
        "/api/v1/accounts",
        json={
            "name": name,
            "external_account_id": "123456",
            "broker": "Demo broker",
            "environment": "demo",
            "currency": "USD",
        },
    )
    assert response.status_code == 201
    return response.json()


def make_trade(client, account_id, outcome="win", pnl=120):
    closed_at = datetime.now(UTC)
    is_open = outcome == "open"
    response = client.post(
        "/api/v1/trades",
        json={
            "account_id": account_id,
            "symbol": "xauusd",
            "direction": "Long",
            "strategy": "Breakout",
            "outcome": outcome,
            "pnl": None if is_open else pnl,
            "r_multiple": None if is_open else 1.5,
            "entry_price": 2300,
            "size": 0.1,
            "opened_at": (closed_at - timedelta(minutes=10)).isoformat(),
            "closed_at": None if is_open else closed_at.isoformat(),
            "tags": ["London", "breakout"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_account_create_connection_status_and_foreign_isolation(client):
    register(client)
    account = make_account(client)
    assert client.get("/api/v1/accounts").json()["items"][0]["id"] == account["id"]

    connection = client.get(f"/api/v1/accounts/{account['id']}/connection")
    assert connection.status_code == 200
    assert connection.json()["status"] == "not_configured"
    assert connection.json()["stale"] is True
    assert client.get(f"/api/v1/accounts/{account['id']}/status").json() == connection.json()
    assert client.post(f"/api/v1/accounts/{account['id']}/sync").status_code == 503

    client.post("/api/v1/auth/logout")
    register(client, "other@example.com")
    assert client.get(f"/api/v1/accounts/{account['id']}/connection").status_code == 404
    assert client.get(f"/api/v1/accounts/{account['id']}/history").status_code == 404


def test_mt5_worker_token_sync_is_idempotent_and_account_scoped(client):
    register(client)
    account = make_account(client)
    account_id = account["id"]
    token_response = client.post(
        f"/api/v1/accounts/{account_id}/mt5/connect",
        json={"login": 123456, "password": "secret-pw", "server": "Broker-MT5"},
    )
    assert token_response.status_code == 202
    assert token_response.headers["cache-control"] == "no-store"
    token = token_response.json()["connector_token"]
    worker_headers = {"Authorization": f"Bearer {token}"}

    sync_run_id = token_response.json()["sync_run_id"]
    poll_path = f"/api/v1/connectors/mt5/accounts/{account_id}/sync-request"
    assert client.get(poll_path).status_code == 401
    claimed = client.get(poll_path, headers=worker_headers)
    assert claimed.status_code == 200
    assert claimed.json()["sync_run_id"] == sync_run_id

    payload = {
        "sync_run_id": sync_run_id,
        "external_account_id": "123456",
        "orders": [
            {
                "external_order_id": "order-1",
                "order_type": "buy",
                "volume": 0.1,
                "price": 2300,
                "state": "filled",
                "occurred_at": datetime.now(UTC).isoformat(),
            }
        ],
        "deals": [
            {
                "external_deal_id": "deal-1",
                "position_identifier": "position-1",
                "external_order_id": "order-1",
                "entry_type": "in",
                "symbol": "xauusd",
                "direction": "Long",
                "volume": 0.1,
                "price": 2300,
                "pnl": 12.5,
                "commission": -1,
                "swap": 0,
                "occurred_at": datetime.now(UTC).isoformat(),
            }
        ],
        "positions": [
            {
                "external_position_id": "position-1",
                "position_identifier": "position-1",
                "symbol": "xauusd",
                "direction": "Long",
                "volume": 0.1,
                "entry_price": 2300,
                "current_price": 2310,
                "stop_loss": 2290,
                "take_profit": 2340,
                "floating_pnl": 10,
                "state": "open",
                "observed_at": datetime.now(UTC).isoformat(),
            }
        ],
        "snapshot": {
            "balance": 1000,
            "equity": 1010,
            "margin": 50,
            "free_margin": 960,
            "observed_at": datetime.now(UTC).isoformat(),
        },
    }
    mismatched_login = {**payload, "external_account_id": "999999"}
    assert client.post(
        f"/api/v1/connectors/mt5/accounts/{account_id}/sync",
        json=mismatched_login,
        headers=worker_headers,
    ).status_code == 409
    received = client.post(
        f"/api/v1/connectors/mt5/accounts/{account_id}/sync",
        json=payload,
        headers=worker_headers,
    )
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "completed"
    assert client.get(f"/api/v1/accounts/{account_id}/connection").json()["status"] == "connected"
    history = client.get(f"/api/v1/accounts/{account_id}/history").json()
    assert len(history["orders"]) == len(history["deals"]) == len(history["positions"]) == 1
    assert history["deals"][0]["symbol"] == "XAUUSD"
    assert history["snapshots"][0]["equity"] == 1010
    open_trades = client.get(f"/api/v1/trades?account_id={account_id}&outcome=open").json()
    assert open_trades["total"] == 1
    episode = open_trades["items"][0]
    assert episode["source"] == "mt5"
    assert episode["entry_price"] == 2300
    assert episode["stop_loss"] == 2290
    assert episode["take_profit"] == 2340
    assert episode["floating_pnl"] == 10
    positions = client.get(f"/api/v1/accounts/{account_id}/positions")
    assert positions.status_code == 200
    assert positions.json()[0]["position_identifier"] == "position-1"
    assert positions.json()[0]["current_price"] == 2310

    second_run = client.post(f"/api/v1/accounts/{account_id}/sync").json()["sync_run_id"]
    assert client.get(poll_path, headers=worker_headers).json()["sync_run_id"] == second_run
    partial_payload = {
        **payload,
        "sync_run_id": second_run,
        "deals": [
            *payload["deals"],
            {
                "external_deal_id": "deal-2",
                "position_identifier": "position-1",
                "external_order_id": "order-2",
                "entry_type": "out",
                "symbol": "xauusd",
                "direction": "Short",
                "volume": 0.05,
                "price": 2320,
                "pnl": 50,
                "commission": -1,
                "swap": 0,
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        ],
        "positions": [
            {
                "external_position_id": "position-1",
                "position_identifier": "position-1",
                "symbol": "xauusd",
                "direction": "Long",
                "volume": 0.05,
                "entry_price": 2300,
                "current_price": 2318,
                "stop_loss": 2290,
                "take_profit": 2340,
                "floating_pnl": 9,
                "state": "open",
                "observed_at": datetime.now(UTC).isoformat(),
            }
        ],
    }
    partial = client.post(
        f"/api/v1/connectors/mt5/accounts/{account_id}/sync",
        json=partial_payload,
        headers=worker_headers,
    )
    assert partial.status_code == 200, partial.text
    partial_trade = client.get(f"/api/v1/trades/{episode['id']}").json()
    assert partial_trade["outcome"] == "open"
    assert partial_trade["size"] == 0.05

    third_run = client.post(f"/api/v1/accounts/{account_id}/sync").json()["sync_run_id"]
    assert client.get(poll_path, headers=worker_headers).json()["sync_run_id"] == third_run
    closed_payload = {
        **partial_payload,
        "sync_run_id": third_run,
        "deals": [
            *partial_payload["deals"],
            {
                "external_deal_id": "deal-3",
                "position_identifier": "position-1",
                "external_order_id": "order-3",
                "entry_type": "out",
                "symbol": "xauusd",
                "direction": "Short",
                "volume": 0.05,
                "price": 2340,
                "pnl": 75,
                "commission": -1,
                "swap": -0.5,
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        ],
        "positions": [],
    }
    closed = client.post(
        f"/api/v1/connectors/mt5/accounts/{account_id}/sync",
        json=closed_payload,
        headers=worker_headers,
    )
    assert closed.status_code == 200, closed.text
    closed_trade = client.get(f"/api/v1/trades/{episode['id']}").json()
    assert closed_trade["outcome"] == "win"
    assert closed_trade["pnl"] == 134
    assert closed_trade["gross_pnl"] == 137.5
    assert closed_trade["commission"] == -3
    assert closed_trade["swap"] == -0.5
    assert closed_trade["closed_at"] is not None
    timeline = client.get(f"/api/v1/trades/{episode['id']}/timeline").json()
    assert any(event["event_type"] == "position_closed" for event in timeline)
    assert client.post(
        f"/api/v1/connectors/mt5/accounts/{account_id}/sync",
        json=closed_payload,
        headers=worker_headers,
    ).status_code == 409
    correction_run = client.post(f"/api/v1/accounts/{account_id}/sync").json()["sync_run_id"]
    assert client.get(poll_path, headers=worker_headers).json()["sync_run_id"] == correction_run
    corrected_payload = {
        **closed_payload,
        "sync_run_id": correction_run,
        "deals": [
            {**closed_payload["deals"][0], "pnl": 14},
            *closed_payload["deals"][1:],
        ],
    }
    correction = client.post(
        f"/api/v1/connectors/mt5/accounts/{account_id}/sync",
        json=corrected_payload,
        headers=worker_headers,
    )
    assert correction.status_code == 200, correction.text
    corrected_trade = client.get(f"/api/v1/trades/{episode['id']}").json()
    assert corrected_trade["pnl"] == 135.5
    assert corrected_trade["gross_pnl"] == 139
    rotated = client.post(
        f"/api/v1/accounts/{account_id}/mt5/connect",
        json={"login": 123456, "password": "secret-pw", "server": "Broker-MT5"},
    ).json()
    assert client.get(poll_path, headers=worker_headers).status_code == 401
    assert client.get(
        poll_path,
        headers={"Authorization": f"Bearer {rotated['connector_token']}"},
    ).status_code == 200


def test_trade_journal_review_dashboard_and_analytics(client):
    register(client)
    account = make_account(client)
    trade = make_trade(client, account["id"])

    assert trade["source"] == "user"
    assert trade["symbol"] == "XAUUSD"
    assert set(trade["tags"]) == {"London", "breakout"}
    journal = client.get("/api/v1/trades?symbol=xauusd&outcome=win")
    assert journal.status_code == 200
    assert journal.json()["total"] == 1
    assert client.get(f"/api/v1/trades/{trade['id']}").json()["id"] == trade["id"]
    assert len(client.get(f"/api/v1/trades/{trade['id']}/events").json()) == 1

    summary = client.get("/api/v1/dashboard/summary").json()
    assert summary["closed_trade_count"] == 1
    assert summary["net_pnl"] == 120
    assert summary["pending_review_count"] == 1
    assert client.get("/api/v1/dashboard/recent-trades").json()["items"][0]["id"] == trade["id"]
    assert client.get("/api/v1/analytics/by-strategy").json()[0]["key"] == "Breakout"

    review = client.post(
        f"/api/v1/trades/{trade['id']}/reviews",
        json={
            "plan_adherence": "yes",
            "learning": "Waited for confirmation.",
            "next_action": "Keep the same checklist.",
        },
    )
    assert review.status_code == 201
    assert client.get(f"/api/v1/trades/{trade['id']}/reviews").json()["id"] == review.json()["id"]
    assert client.get("/api/v1/dashboard/summary").json()["pending_review_count"] == 0


def test_open_trades_cannot_claim_realized_pnl_and_foreign_trade_is_hidden(client):
    register(client)
    account = make_account(client)
    open_trade = make_trade(client, account["id"], outcome="open")
    assert open_trade["pnl"] is None
    bad_closed_trade = client.post(
        "/api/v1/trades",
        json={
            "symbol": "EURUSD",
            "direction": "Short",
            "opened_at": datetime.now(UTC).isoformat(),
            "outcome": "loss",
            "pnl": None,
            "closed_at": datetime.now(UTC).isoformat(),
        },
    )
    assert bad_closed_trade.status_code == 422
    assert (
        client.post(
            f"/api/v1/trades/{open_trade['id']}/reviews",
            json={"plan_adherence": "yes", "learning": "x", "next_action": "y"},
        ).status_code
        == 409
    )

    client.post("/api/v1/auth/logout")
    register(client, "other@example.com")
    assert client.get(f"/api/v1/trades/{open_trade['id']}").status_code == 404


def test_manual_trade_lifecycle_and_review_can_be_updated(client):
    register(client)
    account = make_account(client)
    trade = make_trade(client, account["id"], outcome="open")
    closed_at = datetime.now(UTC)
    closed = client.patch(
        f"/api/v1/trades/{trade['id']}",
        json={
            "outcome": "loss",
            "pnl": -32.5,
            "closed_at": closed_at.isoformat(),
            "exit_price": 2292.5,
        },
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["outcome"] == "loss"
    assert closed.json()["pnl"] == -32.5
    review_payload = {
        "plan_adherence": "partly",
        "learning": "Entry was late.",
        "next_action": "Wait for confirmation.",
    }
    created_review = client.post(
        f"/api/v1/trades/{trade['id']}/reviews",
        json=review_payload,
    )
    assert created_review.status_code == 201
    updated = client.patch(
        f"/api/v1/trades/{trade['id']}/reviews",
        json={
            "plan_adherence": "yes",
            "learning": "Followed the revised plan.",
            "next_action": "Repeat the checklist.",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["plan_adherence"] == "yes"
    assert updated.json()["learning"] == "Followed the revised plan."
def test_trade_journal_sections_save_independently_and_enforce_ownership(client):
    register(client)
    account = make_account(client)
    trade = make_trade(client, account["id"], outcome="open")
    journal_path = f"/api/v1/trades/{trade['id']}/journal"
    strategy = client.patch(
        f"{journal_path}/strategy_setup",
        json={"content": {"setup": ["Liquidity sweep"], "thesis": "Reclaim the range."}},
    )
    psychology = client.patch(
        f"{journal_path}/psychology",
        json={"content": {"before": "calm", "during": "focused"}},
    )
    assert strategy.status_code == psychology.status_code == 200
    assert len(client.get(journal_path).json()) == 2
    updated = client.patch(
        f"{journal_path}/strategy_setup",
        json={"content": {"setup": ["FVG"], "thesis": "Updated thesis."}},
    )
    assert updated.status_code == 200
    assert len(client.get(journal_path).json()) == 2
    assert client.patch(
        f"{journal_path}/evidence",
        json={"content": {"note": "x" * 33000}},
    ).status_code == 413

    client.post("/api/v1/auth/logout")
    register(client, "journal-owner@example.com")
    assert client.get(journal_path).status_code == 404


def test_profile_and_preferences_are_persisted_and_validated(client):
    register(client)
    updated_profile = client.patch(
        "/api/v1/me",
        json={
            "experience_level": "intermediate",
            "goals": "Build a consistent review habit.",
            "preferred_instruments": ["XAUUSD"],
            "preferred_sessions": ["London"],
        },
    )
    assert updated_profile.status_code == 200
    assert updated_profile.json()["experience_level"] == "intermediate"
    assert client.get("/api/v1/me").json()["preferred_instruments"] == ["XAUUSD"]

    preferences = client.patch(
        "/api/v1/preferences",
        json={"timezone": "Europe/London", "currency": "GBP", "theme": "dark"},
    )
    assert preferences.status_code == 200
    assert preferences.json()["timezone"] == "Europe/London"
    assert client.patch("/api/v1/preferences", json={"timezone": "Not/AZone"}).status_code == 422


def test_risk_profiles_and_daily_loss_violation(client):
    register(client)
    account = make_account(client)
    make_trade(client, account["id"], outcome="loss", pnl=-200)
    profile = client.put(
        f"/api/v1/accounts/{account['id']}/risk-profile",
        json={"max_daily_loss": 100, "max_trades_per_day": 3},
    )
    assert profile.status_code == 200
    assert client.get("/api/v1/risk/profiles").json()[0]["account_id"] == account["id"]
    violations = client.get("/api/v1/risk/violations").json()
    assert violations[0]["violations"][0]["rule"] == "max_daily_loss"
    assert client.get("/api/v1/analytics/risk").status_code == 200


def test_tradingview_webhook_authentication_and_alert_matching(client):
    register(client)
    account = make_account(client)
    trade = make_trade(client, account["id"])
    assert client.get("/api/v1/integrations/tradingview/token").json() == {"configured": False}
    token_response = client.post("/api/v1/integrations/tradingview/token")
    assert token_response.status_code == 200
    assert client.get("/api/v1/integrations/tradingview/token").json() == {"configured": True}
    webhook_path = token_response.json()["webhook_path"]
    payload = {
        "webhook_token": token_response.json()["webhook_token"],
        "alert_id": "tv-123",
        "symbol": "xauusd",
        "action": "BUY",
        "price": "{{strategy.order.price}}",
        "lots": "{{strategy.order.contracts}}",
        "timeframe": "15m",
        "timestamp": "{{timenow}}",
        "signal": "breakout",
    }
    assert client.post(
        webhook_path, json={**payload, "webhook_token": "invalid-token-" + "x" * 32}
    ).status_code == 401
    received = client.post(webhook_path, json=payload)
    assert received.status_code == 201
    assert received.json()["processing_status"] == "received"
    assert received.json()["payload"]["action"] == "BUY"
    assert received.json()["payload"]["symbol"] == "XAUUSD"
    assert "webhook_token" not in received.json()["payload"]
    assert client.post(webhook_path, json=payload).json()["id"] == received.json()["id"]
    assert client.get("/api/v1/alerts").json()[0]["symbol"] == "XAUUSD"

    matched = client.post(
        f"/api/v1/alerts/{received.json()['id']}/match",
        json={"trade_id": trade["id"]},
    )
    assert matched.status_code == 201
    assert matched.json()["status"] == "matched"
    assert client.post(f"/api/v1/alerts/{received.json()['id']}/dismiss").status_code == 409
    assert client.delete("/api/v1/integrations/tradingview/token").status_code == 204
    assert client.get("/api/v1/integrations/tradingview/token").json() == {"configured": False}
    assert client.post(webhook_path, json={**payload, "alert_id": "revoked"}).status_code == 401

    client.post("/api/v1/auth/logout")
    register(client, "second-trader@example.com")
    second_token = client.post("/api/v1/integrations/tradingview/token").json()["webhook_token"]
    second_alert = client.post(
        webhook_path,
        json={
            "webhook_token": second_token,
            "alert_id": "tv-second-user",
            "symbol": "EURUSD",
            "action": "SELL",
        },
    )
    assert second_alert.status_code == 201
    assert [alert["id"] for alert in client.get("/api/v1/alerts").json()] == [
        second_alert.json()["id"]
    ]


def test_plan_accepts_structured_entry_and_target_fields(client):
    register(client)
    response = client.post(
        "/api/v1/plans",
        json={
            "symbol": "XAUUSD",
            "direction": "Long",
            "strategy": "London",
            "thesis": "Reclaim the range.",
            "entry_zone": {"low": "2300", "high": "2305"},
            "stop_loss": 2290,
            "targets": [{"price": "2320", "label": "Target 1"}],
        },
    )
    assert response.status_code == 201
    plan = response.json()
    assert plan["entry_zone"]["low"] == "2300"
    assert plan["stop_loss"] == 2290
    assert len(client.get(f"/api/v1/plans/{plan['id']}/versions").json()) == 1


def test_mt5_connect_stores_encrypted_password_and_serves_worker_login_args(client):
    register(client)
    account_id = make_account(client)["id"]
    connected = client.post(
        f"/api/v1/accounts/{account_id}/mt5/connect",
        json={"login": 592210902, "password": "p@ss", "server": "FxPro-MT5 Demo"},
    )
    assert connected.status_code == 202
    assert "p@ss" not in connected.text
    headers = {"Authorization": f"Bearer {connected.json()['connector_token']}"}
    creds = client.get(
        f"/api/v1/connectors/mt5/accounts/{account_id}/credentials", headers=headers
    )
    assert creds.json() == {
        "login": 592210902,
        "password": "p@ss",
        "server": "FxPro-MT5 Demo",
        "timeout": 60000,
    }
    assert client.delete(f"/api/v1/accounts/{account_id}/mt5/connect").status_code == 204
    assert (
        client.get(f"/api/v1/connectors/mt5/accounts/{account_id}/credentials", headers=headers)
    ).status_code == 401


def test_journal_timeline_accepts_list_content(client):
    register(client)
    trade = make_trade(client, make_account(client)["id"])
    entries = [{"id": "e1", "date": "2026-01-01T00:00:00Z", "stage": "Exit", "emotion": "Confident", "note": "ok"}]
    url = f"/api/v1/trades/{trade['id']}/journal/journal_entries"
    assert client.patch(url, json={"content": entries}).status_code == 200
    sections = client.get(f"/api/v1/trades/{trade['id']}/journal").json()
    assert next(s for s in sections if s["section_key"] == "journal_entries")["content"] == entries
