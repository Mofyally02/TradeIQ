import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from metaapi_cloud_sdk import MetaApi
from sqlalchemy import select

from app.api.mt5_connector import apply_sync
from app.core.config import get_settings
from app.db import SessionLocal
from app.platform_models import AccountConnection, SyncRun, TradingAccount
from app.schemas import MT5SyncPayload

logger = logging.getLogger("tradeiq.metaapi")

ENTRY_TYPES = {
    "DEAL_ENTRY_IN": "in",
    "DEAL_ENTRY_OUT": "out",
    "DEAL_ENTRY_INOUT": "inout",
    "DEAL_ENTRY_OUT_BY": "out_by",
}
_background: set[asyncio.Task] = set()


def metaapi_client() -> MetaApi:
    token = get_settings().metaapi_token
    if not token:
        raise RuntimeError("METAAPI_TOKEN is not configured")
    return MetaApi(token=token)


def provider_name(account_id: str) -> str:
    return f"tradeiq-{account_id}"


def friendly_error(error: Exception) -> str:
    text = str(error)
    if "top up" in text.lower():
        return (
            "The hosted MetaApi plan needs credit before it can deploy MT5 accounts "
            "(MetaApi billing). Ask the admin to top up MetaApi or switch you to the EA method."
        )
    if "E_AUTH" in text or "authenticat" in text.lower():
        return "The broker rejected this login or password. Check them and try again."
    if "E_SRV_NOT_FOUND" in text or "server" in text.lower() and "not found" in text.lower():
        return "That broker server was not found. Use the exact server name shown in MT5."
    if type(error).__name__ == "TooManyRequestsException":
        return (
            "The broker rejected these credentials too many times, so validation is paused "
            "for about an hour. Confirm the login, password and exact server name in your "
            "MT5 terminal, then retry later."
        )
    detail = text.split("(")[0].strip()[:200]
    base = "Could not connect to this MT5 account. Check the login, password and server."
    return f"{base} ({detail})" if detail else base


async def find_account_by_name(api: MetaApi, name: str) -> Any | None:
    accounts = await api.metatrader_account_api.get_accounts_with_infinite_scroll_pagination(
        {"query": name, "limit": 10}
    )
    for item in accounts:
        if item.name == name:
            return item
    return None


def aware(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def direction(kind: str) -> str | None:
    if kind.endswith("_BUY"):
        return "Long"
    if kind.endswith("_SELL"):
        return "Short"
    return None


async def paged(fetch, key: str) -> list[dict]:
    items: list[dict] = []
    offset = 0
    while True:
        page = await fetch(offset, 1000)
        batch = page.get(key) or []
        items.extend(batch)
        if len(batch) < 1000:
            return items
        offset += 1000


def build_payload(
    sync_run_id: UUID,
    info: dict,
    positions: list[dict],
    deals: list[dict],
    orders: list[dict],
    observed_at: datetime,
) -> dict:
    return {
        "sync_run_id": str(sync_run_id),
        "external_account_id": str(info["login"]),
        "orders": [
            {
                "external_order_id": str(item["id"]),
                "order_type": str(item.get("type", "unknown"))[:32],
                "volume": float(item.get("volume") or 0),
                "price": item.get("openPrice"),
                "stop_loss": item.get("stopLoss"),
                "take_profit": item.get("takeProfit"),
                "state": str(item.get("state", "unknown"))[:32],
                "occurred_at": aware(item["time"]).isoformat(),
            }
            for item in orders
            if item.get("time")
        ],
        "deals": [
            {
                "external_deal_id": str(item["id"]),
                "position_identifier": str(item["positionId"]) if item.get("positionId") else None,
                "external_order_id": str(item["orderId"]) if item.get("orderId") else None,
                "entry_type": ENTRY_TYPES.get(item.get("entryType", ""), "in"),
                "symbol": item["symbol"],
                "direction": direction(item["type"]),
                "volume": float(item.get("volume") or 0),
                "price": float(item.get("price") or 0),
                "pnl": float(item.get("profit") or 0),
                "commission": float(item.get("commission") or 0),
                "swap": float(item.get("swap") or 0),
                "occurred_at": aware(item["time"]).isoformat(),
            }
            for item in deals
            if item.get("symbol") and direction(item.get("type", "")) and item.get("time")
        ],
        "positions": [
            {
                "external_position_id": str(item["id"]),
                "position_identifier": str(item["id"]),
                "symbol": item["symbol"],
                "direction": direction(item["type"]),
                "volume": float(item.get("volume") or 0),
                "entry_price": item.get("openPrice"),
                "current_price": item.get("currentPrice"),
                "stop_loss": item.get("stopLoss"),
                "take_profit": item.get("takeProfit"),
                "floating_pnl": item.get("profit"),
                "state": "open",
                "observed_at": observed_at.isoformat(),
            }
            for item in positions
            if direction(item.get("type", ""))
        ],
        "snapshot": {
            "balance": float(info["balance"]),
            "equity": float(info["equity"]),
            "margin": info.get("margin"),
            "free_margin": info.get("freeMargin"),
            "observed_at": observed_at.isoformat(),
        },
    }


async def fetch_from_provider(
    provider_account_id: str, sync_run_id: UUID, start: datetime
) -> dict:
    api = metaapi_client()
    provider_account = await api.metatrader_account_api.get_account(provider_account_id)
    if provider_account.state != "DEPLOYED":
        await provider_account.deploy()
    await provider_account.wait_connected(timeout_in_seconds=300)
    connection = provider_account.get_rpc_connection()
    await connection.connect()
    try:
        await connection.wait_synchronized({"timeoutInSeconds": 300})
        end = datetime.now(UTC) + timedelta(minutes=5)
        info = await connection.get_account_information()
        positions = await connection.get_positions()
        deals = await paged(
            lambda offset, limit: connection.get_deals_by_time_range(start, end, offset, limit),
            "deals",
        )
        orders = await paged(
            lambda offset, limit: connection.get_history_orders_by_time_range(
                start, end, offset, limit
            ),
            "historyOrders",
        )
    finally:
        await connection.close()
    return build_payload(sync_run_id, info, positions, deals, orders, datetime.now(UTC))


async def run_sync(account_id: str) -> None:
    """Pull balance, positions and history for one account and store them."""
    settings = get_settings()
    with SessionLocal() as db:
        account = db.get(TradingAccount, account_id)
        connection = db.get(AccountConnection, account_id)
        if account is None or connection is None or not connection.provider_account_id:
            return
        for stuck in db.scalars(
            select(SyncRun).where(
                SyncRun.account_id == account_id, SyncRun.status == "processing"
            )
        ):
            if aware(stuck.started_at) > datetime.now(UTC) - timedelta(minutes=15):
                return
            stuck.status = "failed"
            stuck.error = "Sync timed out"
        db.flush()
        run = db.scalar(
            select(SyncRun)
            .where(SyncRun.account_id == account_id, SyncRun.status == "queued")
            .order_by(SyncRun.started_at)
            .limit(1)
        )
        if run is None:
            run = SyncRun(account_id=account_id, status="queued")
            db.add(run)
            db.flush()
        run.status = "processing"
        run.started_at = datetime.now(UTC)
        connection.status = "syncing"
        provider_id = connection.provider_account_id
        run_id = UUID(str(run.id))
        if connection.last_synced_at is not None:
            start = aware(connection.last_synced_at) - timedelta(days=2)
        else:
            start = datetime.now(UTC) - timedelta(days=settings.metaapi_history_days)
        db.commit()
        try:
            data = await fetch_from_provider(provider_id, run_id, start)
            apply_sync(account, MT5SyncPayload.model_validate(data), db)
        except Exception as error:
            logger.exception("MetaApi sync failed for account %s", account_id)
            db.rollback()
            run = db.get(SyncRun, str(run_id))
            connection = db.get(AccountConnection, account_id)
            message = f"{friendly_error(error)} ({type(error).__name__})"[:2000]
            if run is not None:
                run.status = "failed"
                run.error = message
                run.completed_at = datetime.now(UTC)
            if connection is not None:
                connection.status = "error"
                connection.last_error = message
            db.commit()


async def provision_and_sync(account_id: str, spec: dict[str, Any]) -> None:
    """Create or update the hosted MT5 account (broker validation can take minutes), then sync."""
    try:
        api = metaapi_client()
        with SessionLocal() as db:
            connection = db.get(AccountConnection, account_id)
            existing_id = connection.provider_account_id if connection else None
        provider_account = None
        if existing_id:
            provider_account = await api.metatrader_account_api.get_account(existing_id)
        else:
            provider_account = await find_account_by_name(api, spec["name"])
        if provider_account is None:
            provider_account = await api.metatrader_account_api.create_account(spec)
        else:
            await provider_account.update(
                {k: spec[k] for k in ("name", "password", "server", "manualTrades")}
            )
        with SessionLocal() as db:
            connection = db.get(AccountConnection, account_id)
            if connection is None:
                await provider_account.remove()
                return
            connection.provider_account_id = str(provider_account.id)
            db.commit()
    except Exception as error:
        logger.exception("MetaApi provisioning failed for account %s", account_id)
        message = friendly_error(error)
        with SessionLocal() as db:
            connection = db.get(AccountConnection, account_id)
            if connection is not None:
                connection.status = "error"
                connection.last_error = message
            for run in db.scalars(
                select(SyncRun).where(
                    SyncRun.account_id == account_id, SyncRun.status == "queued"
                )
            ):
                run.status = "failed"
                run.error = message
                run.completed_at = datetime.now(UTC)
            db.commit()
        return
    await run_sync(account_id)


def schedule_provision(account_id: str, spec: dict[str, Any]) -> None:
    task = asyncio.get_running_loop().create_task(provision_and_sync(account_id, spec))
    _background.add(task)
    task.add_done_callback(_background.discard)


def schedule_sync(account_id: str) -> None:
    task = asyncio.get_running_loop().create_task(run_sync(account_id))
    _background.add(task)
    task.add_done_callback(_background.discard)


async def sync_all_loop() -> None:
    interval = get_settings().metaapi_sync_interval_seconds
    while True:
        await asyncio.sleep(interval)
        try:
            with SessionLocal() as db:
                ids = db.scalars(
                    select(AccountConnection.account_id).where(
                        AccountConnection.provider_account_id.is_not(None),
                        AccountConnection.status.in_(["connected", "error"]),
                    )
                ).all()
            for account_id in ids:
                await run_sync(str(account_id))
        except Exception:
            logger.exception("MetaApi periodic sync failed")
