from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TradePlanVersion


def register(client, email="trader@example.com"):
    response = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Trader", "email": email, "password": "long-enough-password"},
    )
    assert response.status_code == 201
    return response.json()


def create_plan(client, symbol="xauusd", thesis="Wait for a confirmed reclaim."):
    return client.post(
        "/api/v1/plans",
        json={
            "symbol": symbol,
            "direction": "Long",
            "strategy": " London breakout ",
            "thesis": thesis,
        },
    )


def test_plan_routes_require_authentication(client):
    assert client.get("/api/v1/plans").status_code == 401
    assert create_plan(client).status_code == 401


def test_create_list_update_discard_plan_and_keep_versions(client, test_engine):
    register(client)
    created = create_plan(client)
    assert created.status_code == 201
    plan = created.json()
    assert plan["symbol"] == "XAUUSD"
    assert plan["strategy"] == "London breakout"
    assert plan["state"] == "planned"

    listed = client.get("/api/v1/plans?state=planned")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [plan["id"]]

    updated = client.patch(
        f"/api/v1/plans/{plan['id']}",
        json={"thesis": "Wait for a close above the level."},
    )
    assert updated.status_code == 200
    assert updated.json()["thesis"] == "Wait for a close above the level."

    discarded = client.post(f"/api/v1/plans/{plan['id']}/discard")
    assert discarded.status_code == 200
    assert discarded.json()["state"] == "discarded"
    assert client.post(f"/api/v1/plans/{plan['id']}/discard").status_code == 409
    assert (
        client.patch(f"/api/v1/plans/{plan['id']}", json={"strategy": "New setup"}).status_code
        == 409
    )
    assert client.get("/api/v1/plans?state=planned").json()["items"] == []

    with Session(test_engine) as session:
        versions = session.scalars(
            select(TradePlanVersion).where(TradePlanVersion.plan_id == UUID(plan["id"]))
        ).all()
        assert len(versions) == 3
        assert [version.version_number for version in versions] == [1, 2, 3]


def test_users_cannot_read_or_list_another_users_plans(client):
    register(client)
    plan = create_plan(client).json()
    client.post("/api/v1/auth/logout")
    register(client, email="another@example.com")

    assert client.get(f"/api/v1/plans/{plan['id']}").status_code == 404
    assert client.patch(f"/api/v1/plans/{plan['id']}", json={"thesis": "Tamper"}).status_code == 404
    assert client.get("/api/v1/plans").json()["items"] == []


def test_invalid_plan_payload_and_empty_patch_are_rejected(client):
    register(client)
    invalid = client.post(
        "/api/v1/plans",
        json={"symbol": " ", "direction": "Sideways", "strategy": "", "thesis": ""},
    )
    assert invalid.status_code == 422

    plan = create_plan(client).json()
    assert client.patch(f"/api/v1/plans/{plan['id']}", json={}).status_code == 422
    assert client.patch(f"/api/v1/plans/{plan['id']}", json={"thesis": None}).status_code == 422

