from sqlalchemy import update
from sqlalchemy.orm import Session

from app.platform_models import Trade


def register(client, email):
    response = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Trader", "email": email, "password": "long-enough-password"},
    )
    assert response.status_code == 201


def create_trade(client):
    response = client.post(
        "/api/v1/trades",
        json={
            "symbol": "xauusd",
            "direction": "Long",
            "strategy": "Breakout",
            "notes": "private note",
            "tags": ["london"],
            "opened_at": "2026-01-05T08:00:00Z",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_delete_trade_removes_it_and_its_journal(client):
    register(client, "delete@example.com")
    trade_id = create_trade(client)
    client.patch(f"/api/v1/trades/{trade_id}/journal/notes", json={"content": {"text": "hello"}})

    assert client.delete(f"/api/v1/trades/{trade_id}").status_code == 204
    assert client.get(f"/api/v1/trades/{trade_id}").status_code == 404
    assert client.delete(f"/api/v1/trades/{trade_id}").status_code == 404


def test_clear_journal_keeps_trade_but_removes_notes(client):
    register(client, "clear@example.com")
    trade_id = create_trade(client)
    client.patch(f"/api/v1/trades/{trade_id}/journal/notes", json={"content": {"text": "hello"}})

    response = client.delete(f"/api/v1/trades/{trade_id}/journal")
    assert response.status_code == 200
    body = response.json()
    assert body["notes"] is None
    assert body["strategy"] == "Uncategorized"
    assert body["tags"] == []
    assert client.get(f"/api/v1/trades/{trade_id}/journal").json() == []


def test_broker_synced_trade_cannot_be_deleted(client, test_engine):
    register(client, "broker@example.com")
    trade_id = create_trade(client)
    with Session(test_engine) as db:
        db.execute(update(Trade).where(Trade.id == trade_id).values(source="mt5"))
        db.commit()

    assert client.delete(f"/api/v1/trades/{trade_id}").status_code == 409
    assert client.get(f"/api/v1/trades/{trade_id}").status_code == 200


def test_cannot_delete_another_users_trade(client):
    register(client, "owner@example.com")
    trade_id = create_trade(client)
    client.post("/api/v1/auth/logout")
    register(client, "other@example.com")

    assert client.delete(f"/api/v1/trades/{trade_id}").status_code == 404
    assert client.delete(f"/api/v1/trades/{trade_id}/journal").status_code == 404
