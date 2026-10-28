"""Per-user device connector: detects MT5 logins seen by the user's terminal and links them on consent."""
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import User
from app.platform_models import (
    AccountConnection,
    DetectedAccount,
    DeviceConnector,
    TradingAccount,
)
from app.services.credentials import decrypt_secret, encrypt_secret
from app.services import ea

MAX_STORED_DEALS = 5000
LIVE_STATES = ("connected", "offline", "pending", "syncing")


def device_url(user_id: str, secret: str) -> str:
    base = get_settings().public_api_url.rstrip("/")
    return f"{base}/api/v1/mt5/device/{user_id}/{secret}"


def issue_connector(db: Session, user: User, rotate: bool = False) -> str:
    """Return the user's connector secret, creating it on first use.

    The secret is stored encrypted so installers can be re-issued without
    breaking a bridge that is already running.
    """
    connector = db.get(DeviceConnector, str(user.id))
    if connector is not None and connector.encrypted_secret and not rotate:
        existing = decrypt_secret(connector.encrypted_secret)
        if existing:
            return existing
    secret = ea.new_secret()
    if connector is None:
        connector = DeviceConnector(user_id=str(user.id), token_hash="")
        db.add(connector)
    connector.token_hash = ea.hash_secret(secret)
    connector.encrypted_secret = encrypt_secret(secret)
    db.commit()
    return secret


def is_active(db: Session, user_id: str, within_minutes: int = 10) -> bool:
    connector = db.get(DeviceConnector, user_id)
    if connector is None or connector.last_seen_at is None:
        return False
    seen = connector.last_seen_at
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)
    return datetime.now(UTC) - seen < timedelta(minutes=within_minutes)


def authenticate(db: Session, user_id: str, secret: str) -> DeviceConnector:
    connector = db.get(DeviceConnector, user_id)
    if connector is None or not hmac.compare_digest(connector.token_hash, ea.hash_secret(secret)):
        raise HTTPException(status_code=403, detail="Invalid webhook")
    return connector


def _find_account(db: Session, user_id: str, login: str) -> TradingAccount | None:
    return db.scalar(
        select(TradingAccount).where(
            TradingAccount.user_id == user_id,
            TradingAccount.external_account_id == login,
            TradingAccount.archived_at.is_(None),
        )
    )


def _merge(stored: dict[str, Any] | None, data: dict[str, Any]) -> dict[str, Any]:
    """Keep the latest snapshot while accumulating deals until the user connects the account."""
    merged = dict(data)
    deals = {str(d.get("ticket")): d for d in (stored or {}).get("deals", [])}
    deals.update({str(d.get("ticket")): d for d in data.get("deals", [])})
    merged["deals"] = list(deals.values())[-MAX_STORED_DEALS:]
    if "positions" not in data and stored and "positions" in stored:
        merged["positions"] = stored["positions"]
    return merged


def _safe_diagnostics(data: dict[str, Any], login: str) -> dict[str, object] | None:
    raw = data.get("diagnostics")
    if not isinstance(raw, dict):
        return None
    error_code = raw.get("last_error_code")
    http_status = raw.get("http_status")
    return {
        "ea_version": str(raw.get("ea_version") or "")[:24],
        "terminal_id": str(raw.get("terminal_id") or "")[:64],
        "login": login[:64],
        "last_error_code": error_code if isinstance(error_code, int) and not isinstance(error_code, bool) else None,
        "http_status": http_status if isinstance(http_status, int) and not isinstance(http_status, bool) else None,
        "last_result": str(raw.get("last_result") or "")[:240],
        "received_at": datetime.now(UTC).isoformat(),
    }


def handle_push(db: Session, connector: DeviceConnector, data: dict[str, Any]) -> dict[str, Any]:
    login = str(data.get("account") or "").strip()
    if not login:
        raise ValueError("Missing account login")
    user_id = str(connector.user_id)
    connector.last_seen_at = datetime.now(UTC)
    diagnostics = _safe_diagnostics(data, login)
    if diagnostics is not None:
        connector.last_diagnostics = diagnostics
    account = _find_account(db, user_id, login)
    connection = db.get(AccountConnection, str(account.id)) if account else None
    if account and connection and connection.connector_type == "ea" and connection.status in LIVE_STATES:
        result = ea.ingest(account, connection, data, db)
        return {"state": "connected", **result}

    detected = db.scalar(
        select(DetectedAccount).where(DetectedAccount.user_id == user_id, DetectedAccount.login == login)
    )
    if detected is None:
        detected = DetectedAccount(user_id=user_id, login=login)
        db.add(detected)
    if detected.status == "connected":
        detected.status = "pending"
    detected.server = str(data.get("server") or "")[:120] or detected.server
    detected.name = str(data.get("name") or "")[:120] or detected.name
    detected.currency = str(data.get("currency") or "")[:3] or detected.currency
    detected.balance = data.get("balance")
    detected.equity = data.get("equity")
    detected.last_seen_at = datetime.now(UTC)
    detected.payload = _merge(detected.payload, data)
    db.commit()
    return {"state": "detected"}


def _unique_name(db: Session, user_id: str, wanted: str) -> str:
    taken = set(db.scalars(select(TradingAccount.name).where(TradingAccount.user_id == user_id)))
    name, n = wanted, 2
    while name in taken:
        name, n = f"{wanted} ({n})", n + 1
    return name


def claim(db: Session, user: User, detected: DetectedAccount, login: str, server: str) -> TradingAccount:
    """Connect a detected account after the user re-enters its login and server."""
    if login.strip() != detected.login:
        raise HTTPException(status_code=422, detail="The login number does not match the detected account.")
    if detected.server and server.strip().lower() != detected.server.lower():
        raise HTTPException(status_code=422, detail="The server does not match the detected account.")
    user_id = str(user.id)
    account = _find_account(db, user_id, detected.login)
    if account is None:
        label = detected.name or f"MT5 {detected.login}"
        account = TradingAccount(
            user_id=user_id,
            name=_unique_name(db, user_id, label),
            external_account_id=detected.login,
            server_name=detected.server,
            currency=(detected.currency or "USD").upper(),
            environment="demo" if "demo" in (detected.server or "").lower() else "live",
            account_type="standard",
        )
        db.add(account)
        db.flush()
    connection = db.get(AccountConnection, str(account.id))
    if connection is None:
        connection = AccountConnection(account_id=account.id)
        db.add(connection)
    connection.connector_type = "ea"
    connection.connector_token_hash = None
    connection.encrypted_password = None
    connection.provider_account_id = None
    connection.status = "pending"
    connection.last_error = None
    db.flush()
    if detected.payload:
        ea.ingest(account, connection, detected.payload, db)
    detected.status = "connected"
    detected.payload = None
    db.commit()
    db.refresh(account)
    return account
