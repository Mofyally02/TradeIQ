import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from tests.test_platform_features import make_account, register


def promote(test_engine, email):
    with Session(test_engine) as db:
        db.scalar(select(User).where(User.email == email)).role = "admin"
        db.commit()


def test_user_cannot_use_ea_unless_admin_enables_it(client):
    register(client)
    account_id = make_account(client)["id"]
    assert client.get("/api/v1/platform/mt5-method").json() == {"method": "metaapi"}
    assert client.post(f"/api/v1/accounts/{account_id}/ea/connect").status_code == 403


def test_admin_switch_enables_ea_flow(client, test_engine):
    register(client, "boss@example.com")
    promote(test_engine, "boss@example.com")
    assert client.put("/api/v1/admin/settings", json={"method": "ea"}).status_code == 200
    account_id = make_account(client)["id"]
    connect = client.post(f"/api/v1/accounts/{account_id}/ea/connect")
    assert connect.status_code == 201
    url = connect.json()["webhook_url"]
    path = url.split("localhost:8000", 1)[1]
    now = int(time.time())
    push = {
        "account": 123456,
        "balance": 1000,
        "equity": 1010,
        "margin": 10,
        "free_margin": 990,
        "server_offset": 0,
        "positions": [
            {"ticket": 7, "position_id": 7, "symbol": "EURUSD", "type": "buy", "volume": 0.1,
             "open_price": 1.1, "current_price": 1.2, "profit": 10, "sl": 0, "tp": 0}
        ],
        "deals": [
            {"ticket": 70, "position_id": 7, "order": 70, "symbol": "EURUSD", "type": "buy",
             "entry": "in", "volume": 0.1, "price": 1.1, "profit": 0, "commission": -0.7,
             "swap": 0, "time": now - 60},
            {"ticket": 71, "position_id": 0, "symbol": "", "type": "balance", "time": now},
        ],
    }
    assert client.post(path, json=push).status_code == 200
    status = client.get(f"/api/v1/accounts/{account_id}/status").json()
    assert status["connector_type"] == "ea"
    assert status["status"] == "connected"
    assert status["balance"] == 1000 and status["equity"] == 1010
    for os_name, marker in (("mac", "#!/bin/bash"), ("windows", "#PSBEGIN#")):
        script = client.get(connect.json()["installers"][os_name].split("localhost:8000", 1)[1])
        assert script.status_code == 200 and marker in script.text and url in script.text
    assert "TradeIQ" in client.get(path + "/ea.mq5").text
    assert client.get(path[:-4] + "xxxx/installer/mac").status_code == 403
    assert client.patch(f"/api/v1/accounts/{account_id}", json={"name": "Renamed"}).json()["name"] == "Renamed"
    positions = client.get(f"/api/v1/accounts/{account_id}/positions").json()
    assert len(positions) == 1
    bad = path[:-4] + "xxxx"
    assert client.post(bad, json=push).status_code == 403
    assert client.post(path, json={**push, "account": 999}).json()["state"] == "detected"
    # With the connector already running, adding another account needs no new installer.
    second = client.post("/api/v1/accounts", json={
        "name": "Second", "external_account_id": "777", "broker": "Demo broker",
        "environment": "demo", "currency": "USD"}).json()["id"]
    again = client.post(f"/api/v1/accounts/{second}/ea/connect").json()
    assert again["already_installed"] is True and again["webhook_url"] == url
    assert client.post(path, json={**push, "account": 777}).json()["state"] == "connected"
    assert client.get(f"/api/v1/accounts/{second}/status").json()["status"] == "connected"


def test_admin_endpoints_require_admin_and_switch_user(client, test_engine):
    register(client, "user@example.com")
    assert client.get("/api/v1/admin/users").status_code == 403
    client.post("/api/v1/auth/logout")
    register(client, "boss@example.com")
    promote(test_engine, "boss@example.com")
    users = client.get("/api/v1/admin/users").json()
    target = next(u for u in users if u["email"] == "user@example.com")
    result = client.put(f"/api/v1/admin/users/{target['id']}/mt5-method", json={"method": "ea"})
    assert result.status_code == 200 and result.json()["method"] == "ea"
    assert client.get("/api/v1/admin/overview").json()["users"] == 2


def test_device_detects_and_claims_multiple_accounts(client, test_engine):
    register(client, "multi@example.com")
    promote(test_engine, "multi@example.com")
    client.put("/api/v1/admin/settings", json={"method": "ea"})
    connector = client.post("/api/v1/devices/connector").json()
    path = connector["webhook_url"].split("localhost:8000", 1)[1]
    now = int(time.time())

    def push(login, balance, deals=()):
        return client.post(path, json={
            "account": login, "server": "Demo-1", "name": f"Acc {login}", "currency": "USD",
            "balance": balance, "equity": balance, "server_offset": 0,
            "positions": [], "deals": list(deals),
        })

    deal = {"ticket": 5, "position_id": 5, "order": 5, "symbol": "EURUSD", "type": "buy",
            "entry": "in", "volume": 0.1, "price": 1.1, "profit": 0, "commission": 0, "swap": 0, "time": now - 60}
    assert push(111, 1000, [deal]).json()["state"] == "detected"
    assert push(222, 2000).json()["state"] == "detected"
    detected = client.get("/api/v1/devices/detected").json()
    assert {d["login"] for d in detected} == {"111", "222"}
    first = next(d for d in detected if d["login"] == "111")
    assert client.post(f"/api/v1/devices/detected/{first['id']}/connect", json={"login": "999", "server": "Demo-1"}).status_code == 422
    ok = client.post(f"/api/v1/devices/detected/{first['id']}/connect", json={"login": "111", "server": "demo-1"})
    assert ok.status_code == 201
    account_id = ok.json()["id"]
    status = client.get(f"/api/v1/accounts/{account_id}/status").json()
    assert status["status"] == "connected" and status["balance"] == 1000
    assert push(111, 1100).json()["state"] == "connected"
    assert [d["login"] for d in client.get("/api/v1/devices/detected").json()] == ["222"]
    second = client.get("/api/v1/devices/detected").json()[0]
    assert client.post(f"/api/v1/devices/detected/{second['id']}/dismiss").status_code == 204
    assert client.get("/api/v1/devices/detected").json() == []
    assert client.post(path[:-4] + "xxxx", json={"account": 1}).status_code == 403
