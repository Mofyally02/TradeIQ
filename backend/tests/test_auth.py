from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserSession


def test_register_me_and_logout(client):
    registered = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Trader", "email": "Trader@example.com", "password": "long-enough-password"},
    )

    assert registered.status_code == 201
    assert registered.json()["email"] == "trader@example.com"
    assert "tradeiq_session" in registered.cookies
    assert "httponly" in registered.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/me").json()["id"] == registered.json()["id"]

    logged_out = client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_duplicate_email_is_rejected(client):
    payload = {"full_name": "Test Trader", "email": "trader@example.com", "password": "long-enough-password"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201

    duplicate = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Trader", "email": "TRADER@example.com", "password": "another-long-password"},
    )
    assert duplicate.status_code == 409


def test_login_rejects_invalid_password(client):
    client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Trader", "email": "trader@example.com", "password": "long-enough-password"},
    )
    client.post("/api/v1/auth/logout")

    response = client.post(
        "/api/v1/auth/login",
        json={"full_name": "Test Trader", "email": "trader@example.com", "password": "incorrect-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Email or password is incorrect"


def test_login_starts_a_valid_session(client):
    client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Trader", "email": "trader@example.com", "password": "long-enough-password"},
    )
    client.post("/api/v1/auth/logout")

    response = client.post(
        "/api/v1/auth/login",
        json={"full_name": "Test Trader", "email": "trader@example.com", "password": "long-enough-password"},
    )
    assert response.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200


def test_expired_session_is_rejected(client, test_engine):
    client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Trader", "email": "trader@example.com", "password": "long-enough-password"},
    )
    with Session(test_engine) as session:
        record = session.scalar(select(UserSession))
        record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()

    assert client.get("/api/v1/auth/me").status_code == 401


def test_register_requires_a_long_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Trader", "email": "trader@example.com", "password": "too-short"},
    )
    assert response.status_code == 422


def test_cross_origin_mutations_are_rejected(client):
    response = client.post(
        "/api/v1/auth/register",
        headers={"Origin": "https://untrusted.example"},
        json={"full_name": "Test Trader", "email": "trader@example.com", "password": "long-enough-password"},
    )
    assert response.status_code == 403
