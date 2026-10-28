"""Verifies, and where possible completes, an MT5 account connection after the user clicks Connect."""
from datetime import UTC, datetime, timedelta
import ipaddress
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.platform_models import (
    AccountConnection,
    AccountSnapshot,
    DetectedAccount,
    DeviceConnector,
    TradingAccount,
)
from app.core.config import get_settings
from app.services import ea

FRESH = timedelta(minutes=2)
RECENT_DETECTION = timedelta(minutes=10)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _within(value: datetime | None, window: timedelta) -> bool:
    value = _aware(value)
    return value is not None and datetime.now(UTC) - value < window


def _ago(value: datetime | None) -> str:
    value = _aware(value)
    if value is None:
        return "never"
    minutes = int((datetime.now(UTC) - value).total_seconds() // 60)
    return "less than a minute ago" if minutes < 1 else f"{minutes} min ago"


def _step(key: str, label: str, status: str, detail: str, fix: str | None = None) -> dict[str, Any]:
    return {"key": key, "label": label, "status": status, "detail": detail, "fix": fix}


def _heartbeat_fix() -> str:
    fix = (
        "Open MT5, sign in to this account, enable Algo Trading, and confirm the "
        "TradeIQ_Journal EA is attached to a chart. Check its on-chart diagnostic and the "
        "MT5 Experts tab; when using the Windows file bridge, also check "
        "%USERPROFILE%\\.tradeiq\\bridge.log."
    )
    host = urlparse(get_settings().public_api_url).hostname or ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.casefold().rstrip(".") == "localhost"
    if loopback:
        fix += (
            f" The API is configured as {host} (this machine only). If MT5 runs on a "
            "different PC or VM, set PUBLIC_API_URL to the API computer's reachable "
            "LAN address or HTTPS domain, then rerun the installer."
        )
    return fix


def _diagnostic_category(diagnostics: dict[str, object] | None) -> str | None:
    if diagnostics is None:
        return None
    error_code = diagnostics.get("last_error_code")
    http_status = diagnostics.get("http_status")
    if error_code == 4014:
        return "webrequest_blocked"
    if isinstance(error_code, int) and 5200 <= error_code <= 5203:
        return "network_error"
    if http_status in (401, 403):
        return "auth_failed"
    if http_status == 409:
        return "account_mismatch"
    return "last_push_recorded"


def _adopt_detected(db: Session, account: TradingAccount, connection: AccountConnection) -> bool:
    """Link a login the terminal already reported, since the user just asked to connect this account."""
    detected = db.scalar(
        select(DetectedAccount).where(
            DetectedAccount.user_id == str(account.user_id),
            DetectedAccount.login == account.external_account_id,
            DetectedAccount.status == "pending",
        )
    )
    if detected is None or not detected.payload or not _within(detected.last_seen_at, RECENT_DETECTION):
        return False
    connection.connector_type = "ea"
    connection.status = "pending"
    connection.last_error = None
    db.flush()
    ea.ingest(account, connection, detected.payload, db)
    detected.status = "connected"
    detected.payload = None
    db.commit()
    return True


def verify(db: Session, user: User, account: TradingAccount) -> dict[str, Any]:
    connection = db.get(AccountConnection, str(account.id))
    connector = db.get(DeviceConnector, str(user.id))
    diagnostics = connector.last_diagnostics if connector and connector.last_diagnostics else None
    steps: list[dict[str, Any]] = []

    installed = connector is not None and bool(connector.encrypted_secret)
    steps.append(
        _step("connector", "Connection credential ready", "ok", "Your personal connector is ready.")
        if installed
        else _step(
            "connector", "TradeIQ connector installed", "failed",
            "The TradeIQ setup has not been run on this computer.",
            "Download and run the TradeIQ setup file from the connection guide.",
        )
    )

    terminal_ok = installed and _within(connector.last_seen_at, FRESH)
    if terminal_ok:
        detail = "MT5 sent data in the last 2 minutes."
        if diagnostics:
            details = [str(diagnostics.get("ea_version") or "EA version unknown")]
            if diagnostics.get("terminal_id"):
                details.append(f"terminal {diagnostics['terminal_id']}")
            if diagnostics.get("last_result"):
                details.append(f"last result: {diagnostics['last_result']}")
            detail += " Last reported by " + ", ".join(details) + "."
        steps.append(_step("terminal", "MetaTrader 5 is reporting", "ok", detail))
    elif installed and connector.last_seen_at is not None:
        steps.append(
            _step(
                "terminal", "MetaTrader 5 is reporting", "failed",
                f"Nothing received from MT5 (last heard {_ago(connector.last_seen_at)}).",
                _heartbeat_fix(),
            )
        )
    else:
        steps.append(
            _step(
                "terminal", "MetaTrader 5 is reporting", "pending",
                "Waiting for the first heartbeat from the TradeIQ EA.",
                _heartbeat_fix(),
            )
        )

    healed = False
    if connection is not None and terminal_ok and not _within(connection.last_synced_at, FRESH):
        healed = _adopt_detected(db, account, connection)
        if healed:
            db.refresh(connection)

    login_ok = connection is not None and _within(connection.last_synced_at, FRESH) and connection.status in (
        "connected", "syncing",
    )
    if login_ok:
        detail = "Login matched and linked automatically." if healed else "MT5 is signed in to this account."
        steps.append(_step("login", f"Signed in to account {account.external_account_id or ''}".strip(), "ok", detail))
    elif terminal_ok:
        seen = db.scalars(
            select(DetectedAccount.login).where(
                DetectedAccount.user_id == str(user.id), DetectedAccount.status == "pending"
            )
        ).all()
        other = f" MT5 is currently signed in to {', '.join(seen)}." if seen else ""
        reported_login = str(diagnostics.get("login") or "") if diagnostics else ""
        if reported_login and account.external_account_id and reported_login != account.external_account_id:
            other += f" The latest accepted EA heartbeat reported login {reported_login}."
        terminal_id = str(diagnostics.get("terminal_id") or "") if diagnostics else ""
        if terminal_id:
            other += f" Terminal ID: {terminal_id}."
        steps.append(
            _step(
                "login", f"Signed in to account {account.external_account_id or ''}".strip(), "failed",
                "MT5 is reporting, but not for this account." + other,
                f"In MetaTrader 5 choose File → Login to Trade Account and sign in to {account.external_account_id or 'this account'}.",
            )
        )
    else:
        steps.append(_step("login", "Signed in to this account", "pending", "Waiting for MT5."))

    snapshot = db.scalar(
        select(AccountSnapshot).where(AccountSnapshot.account_id == account.id)
        .order_by(AccountSnapshot.observed_at.desc()).limit(1)
    )
    if login_ok and snapshot is not None:
        steps.append(_step("data", "Account data importing", "ok", f"Balance {float(snapshot.balance):,.2f} {account.currency}."))
    else:
        steps.append(_step("data", "Account data importing", "pending", "Waiting for balance and trade history."))

    failed = next((s for s in steps if s["status"] == "failed"), None)
    connected = all(s["status"] == "ok" for s in steps)
    return {
        "account_id": str(account.id),
        "state": "connected" if connected else "action_required" if failed else "waiting",
        "connected": connected,
        "auto_linked": healed,
        "diagnostics": {
            **diagnostics,
            "category": _diagnostic_category(diagnostics),
        } if diagnostics else None,
        "headline": (
            "Connected. Your account is live." if connected
            else failed["detail"] if failed else "Checking your MetaTrader 5 connection…"
        ),
        "steps": steps,
    }
