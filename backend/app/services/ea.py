import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.mt5_connector import apply_sync
from app.core.config import get_settings
from app.platform_models import (
    AccountConnection,
    AccountSnapshot,
    MT5Position,
    SyncRun,
    TradingAccount,
)
from app.schemas import MT5SyncPayload

ENTRY_TYPES = {"in", "out", "inout", "out_by"}


def new_secret() -> str:
    return secrets.token_urlsafe(36)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def secret_matches(connection: AccountConnection, presented: str) -> bool:
    return (
        connection.connector_type == "ea"
        and connection.connector_token_hash is not None
        and hmac.compare_digest(connection.connector_token_hash, hash_secret(presented))
    )


def webhook_url(account_id: str, secret: str) -> str:
    base = get_settings().public_api_url.rstrip("/")
    return f"{base}/api/v1/mt5/ea/{account_id}/{secret}"


def to_utc(value: Any, offset_seconds: int) -> datetime:
    """EA timestamps are MT5 server-time epoch seconds; subtract the server's GMT offset."""
    return datetime.fromtimestamp(int(value) - offset_seconds, UTC)


def side(kind: str) -> str:
    return "Long" if str(kind).lower() == "buy" else "Short"


def build_payload(account: TradingAccount, data: dict[str, Any], db: Session, run_id: Any) -> dict:
    offset = int(data.get("server_offset") or 0)
    now = datetime.now(UTC)
    deals = []
    for item in data.get("deals") or []:
        if str(item.get("type", "")).lower() not in ("buy", "sell"):
            continue
        entry = str(item.get("entry", "in")).lower()
        deals.append(
            {
                "external_deal_id": str(item["ticket"]),
                "position_identifier": str(item["position_id"]) if item.get("position_id") else None,
                "external_order_id": str(item["order"]) if item.get("order") else None,
                "entry_type": entry if entry in ENTRY_TYPES else "in",
                "symbol": item["symbol"],
                "direction": side(item["type"]),
                "volume": float(item.get("volume") or 0),
                "price": float(item.get("price") or 0),
                "pnl": float(item["profit"]) if item.get("profit") is not None else None,
                "commission": float(item["commission"]) if item.get("commission") is not None else None,
                "swap": float(item["swap"]) if item.get("swap") is not None else None,
                "occurred_at": to_utc(item["time"], offset),
            }
        )
    if data.get("positions") is not None:
        positions = [
            {
                "external_position_id": str(item["ticket"]),
                "position_identifier": str(item.get("position_id") or item["ticket"]),
                "symbol": item["symbol"],
                "direction": side(item["type"]),
                "volume": float(item.get("volume") or 0),
                "entry_price": item.get("open_price"),
                "current_price": item.get("current_price"),
                "stop_loss": item.get("sl") or None,
                "take_profit": item.get("tp") or None,
                "floating_pnl": item.get("profit"),
                "state": "open",
                "observed_at": now,
            }
            for item in data["positions"]
        ]
    else:
        # History-only batches must not close positions the batch says nothing about.
        positions = [
            {
                "external_position_id": row.external_position_id,
                "position_identifier": row.external_position_id,
                "symbol": row.symbol,
                "direction": row.direction,
                "volume": float(row.volume),
                "entry_price": float(row.entry_price) if row.entry_price is not None else None,
                "current_price": float(row.current_price) if row.current_price is not None else None,
                "stop_loss": float(row.stop_loss) if row.stop_loss is not None else None,
                "take_profit": float(row.take_profit) if row.take_profit is not None else None,
                "floating_pnl": float(row.floating_pnl) if row.floating_pnl is not None else None,
                "state": "open",
                "observed_at": now,
            }
            for row in db.scalars(
                select(MT5Position).where(
                    MT5Position.account_id == account.id, MT5Position.state == "open"
                )
            )
        ]
    last = db.scalar(
        select(AccountSnapshot)
        .where(AccountSnapshot.account_id == account.id)
        .order_by(AccountSnapshot.observed_at.desc())
        .limit(1)
    )
    balance = data.get("balance", float(last.balance) if last else 0)
    equity = data.get("equity", float(last.equity) if last else balance)
    return {
        "sync_run_id": run_id,
        "external_account_id": account.external_account_id,
        "deals": deals,
        "positions": positions,
        "snapshot": {
            "balance": balance,
            "equity": equity,
            "margin": data.get("margin"),
            "free_margin": data.get("free_margin"),
            "observed_at": now,
        },
    }


def ingest(account: TradingAccount, connection: AccountConnection, data: dict, db: Session) -> dict:
    """Store one EA push. The account login is learned from the first push."""
    login = str(data.get("account") or "")
    if not login:
        raise ValueError("Missing account login")
    if not account.external_account_id:
        account.external_account_id = login
    elif account.external_account_id != login:
        raise PermissionError("This webhook belongs to a different MT5 login")
    for run in db.scalars(
        select(SyncRun).where(SyncRun.account_id == account.id, SyncRun.status == "processing")
    ):
        run.status = "failed"
        run.error = "Superseded"
    run = SyncRun(account_id=account.id, status="processing", started_at=datetime.now(UTC))
    db.add(run)
    db.flush()
    payload = MT5SyncPayload.model_validate(build_payload(account, data, db, run.id))
    return apply_sync(account, payload, db)
