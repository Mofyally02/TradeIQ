import hashlib
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Database
from app.platform_models import (
    AccountConnection,
    AccountSnapshot,
    MT5Deal,
    MT5Order,
    MT5Position,
    SyncRun,
    Trade,
    TradeEvent,
    TradingAccount,
)
from app.schemas import MT5SyncFailure, MT5SyncPayload
from app.services.credentials import decrypt_secret

router = APIRouter(prefix="/connectors/mt5", tags=["MT5 connector"])


def authenticate_connector(
    account_id: UUID,
    db: Database,
    authorization: Annotated[str | None, Header()] = None,
) -> TradingAccount:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Connector bearer token required")
    token_hash = hashlib.sha256(authorization.removeprefix("Bearer ").encode("utf-8")).hexdigest()
    account = db.scalar(
        select(TradingAccount)
        .join(AccountConnection, AccountConnection.account_id == TradingAccount.id)
        .where(
            TradingAccount.id == account_id,
            TradingAccount.archived_at.is_(None),
            AccountConnection.connector_token_hash == token_hash,
        )
    )
    if account is None:
        raise HTTPException(status_code=401, detail="Connector token is invalid")
    return account


ConnectorAccount = Annotated[TradingAccount, Depends(authenticate_connector)]


@router.get("/accounts/{account_id}/credentials")
def get_login_credentials(account: ConnectorAccount, db: Database) -> dict[str, object]:
    """Arguments for mt5.login(login, password=, server=, timeout=)."""
    connection = db.get(AccountConnection, account.id)
    password = (
        decrypt_secret(connection.encrypted_password)
        if connection is not None and connection.encrypted_password
        else None
    )
    if not account.external_account_id or not account.server_name or password is None:
        raise HTTPException(status_code=409, detail="MT5 login, password and server are not set")
    timeout = int((connection.sync_cursor or {}).get("timeout", 60000))
    return {
        "login": int(account.external_account_id),
        "password": password,
        "server": account.server_name,
        "timeout": timeout,
    }


def reconcile_position_episode(
    db: Database,
    account: TradingAccount,
    position_identifier: str,
    active_position: MT5Position | None,
    observed_at: datetime,
) -> Trade | None:
    deals = db.scalars(
        select(MT5Deal)
        .where(
            MT5Deal.account_id == account.id,
            MT5Deal.position_identifier == position_identifier,
        )
        .order_by(MT5Deal.occurred_at, MT5Deal.external_deal_id)
    ).all()
    entries = [deal for deal in deals if deal.entry_type in {"in", "inout"}]
    exits = [deal for deal in deals if deal.entry_type in {"out", "out_by"}]
    if not entries:
        return None

    trade = db.scalar(
        select(Trade).where(
            Trade.account_id == account.id,
            Trade.external_id == position_identifier,
            Trade.source == "mt5",
        )
    )
    was_new = trade is None
    was_open = trade is None or trade.outcome == "open"
    opening_volume = sum(float(deal.volume) for deal in entries)
    closing_volume = sum(float(deal.volume) for deal in exits)
    fully_closed = active_position is None and closing_volume >= opening_volume - 1e-8
    gross_pnl = sum(float(deal.pnl or 0) for deal in deals)
    commission = sum(float(deal.commission or 0) for deal in deals)
    swap = sum(float(deal.swap or 0) for deal in deals)
    net_pnl = gross_pnl + commission + swap
    entry_volume = sum(float(deal.volume) for deal in entries)
    average_entry = (
        sum(float(deal.price) * float(deal.volume) for deal in entries) / entry_volume
        if entry_volume
        else None
    )
    exit_volume = sum(float(deal.volume) for deal in exits)
    average_exit = (
        sum(float(deal.price) * float(deal.volume) for deal in exits) / exit_volume
        if exit_volume
        else None
    )
    if trade is None:
        trade = Trade(
            user_id=account.user_id,
            account_id=account.id,
            symbol=entries[0].symbol,
            direction=entries[0].direction,
            strategy="Uncategorized",
            source="mt5",
            external_id=position_identifier,
            opened_at=entries[0].occurred_at,
        )
        db.add(trade)
        db.flush()
    trade.symbol = entries[0].symbol
    trade.direction = entries[0].direction
    trade.opened_at = entries[0].occurred_at
    trade.entry_price = (
        float(active_position.entry_price)
        if active_position is not None and active_position.entry_price is not None
        else average_entry
    )
    trade.size = (
        float(active_position.volume) if active_position is not None else opening_volume
    )
    trade.exit_price = average_exit if fully_closed else None
    trade.outcome = (
        "win" if net_pnl > 0 else "loss" if net_pnl < 0 else "flat"
    ) if fully_closed else "open"
    trade.pnl = net_pnl if fully_closed else None
    exit_times = [
        deal.occurred_at.replace(tzinfo=UTC)
        if deal.occurred_at.tzinfo is None
        else deal.occurred_at
        for deal in exits
    ]
    trade.closed_at = max(exit_times, default=None) if fully_closed else None
    trade.metadata_json = {
        "gross_pnl": gross_pnl,
        "commission": commission,
        "swap": swap,
        "floating_pnl": (
            float(active_position.floating_pnl)
            if active_position is not None and active_position.floating_pnl is not None
            else None
        ),
    }
    trade.updated_at = observed_at
    if was_new:
        db.add(
            TradeEvent(
                trade_id=trade.id,
                event_type="position_opened",
                source="mt5",
                payload={
                    "position_identifier": position_identifier,
                    "symbol": trade.symbol,
                    "direction": trade.direction,
                    "entry_price": trade.entry_price,
                    "volume": trade.size,
                },
                occurred_at=trade.opened_at,
            )
        )
    if fully_closed and was_open:
        db.add(
            TradeEvent(
                trade_id=trade.id,
                event_type="position_closed",
                source="mt5",
                payload={
                    "gross_pnl": gross_pnl,
                    "commission": commission,
                    "swap": swap,
                    "net_pnl": net_pnl,
                    "closed_at": trade.closed_at.isoformat() if trade.closed_at else None,
                },
                occurred_at=trade.closed_at or observed_at,
            )
        )
    return trade


@router.get("/accounts/{account_id}/sync-request")
def claim_sync_request(
    account: ConnectorAccount,
    db: Database,
) -> dict[str, str] | None:
    run = db.scalar(
        select(SyncRun)
        .where(SyncRun.account_id == account.id, SyncRun.status == "queued")
        .order_by(SyncRun.started_at, SyncRun.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if run is None:
        return None
    run.status = "processing"
    run.started_at = datetime.now(UTC)
    connection = db.get(AccountConnection, account.id)
    if connection is None:
        raise HTTPException(status_code=503, detail="Account connection is unavailable")
    connection.status = "syncing"
    db.commit()
    return {"sync_run_id": str(run.id)}


@router.post("/accounts/{account_id}/sync")
def receive_sync(
    account: ConnectorAccount,
    payload: MT5SyncPayload,
    db: Database,
) -> dict[str, object]:
    return apply_sync(account, payload, db)


def apply_sync(
    account: TradingAccount,
    payload: MT5SyncPayload,
    db: Session,
) -> dict[str, object]:
    if payload.external_account_id != account.external_account_id:
        raise HTTPException(
            status_code=409,
            detail="The connected MT5 login does not match this account's configured login ID",
        )
    run = db.scalar(
        select(SyncRun).where(
            SyncRun.id == payload.sync_run_id,
            SyncRun.account_id == account.id,
            SyncRun.status == "processing",
        )
    )
    if run is None:
        raise HTTPException(status_code=409, detail="Sync request is missing or no longer active")

    changed_position_ids: set[str] = set()
    new_deals: list[MT5Deal] = []
    for item in payload.orders:
        order = db.scalar(
            select(MT5Order).where(
                MT5Order.account_id == account.id,
                MT5Order.external_order_id == item.external_order_id,
            )
        )
        if order is None:
            order = MT5Order(account_id=account.id, external_order_id=item.external_order_id)
            db.add(order)
        order.order_type = item.order_type
        order.volume = item.volume
        order.price = item.price
        order.stop_loss = item.stop_loss
        order.take_profit = item.take_profit
        order.state = item.state
        order.occurred_at = item.occurred_at

    for item in payload.deals:
        deal = db.scalar(
            select(MT5Deal).where(
                MT5Deal.account_id == account.id,
                MT5Deal.external_deal_id == item.external_deal_id,
            )
        )
        is_new_deal = deal is None
        if deal is None:
            deal = MT5Deal(account_id=account.id, external_deal_id=item.external_deal_id)
            db.add(deal)
        previous_position_identifier = deal.position_identifier
        deal_changed = is_new_deal or (
            deal.external_order_id != item.external_order_id
            or deal.position_identifier != item.position_identifier
            or deal.entry_type != item.entry_type
            or deal.symbol != item.symbol.upper()
            or deal.direction != item.direction.value
            or float(deal.volume) != item.volume
            or float(deal.price) != item.price
            or (float(deal.pnl) if deal.pnl is not None else None) != item.pnl
            or (
                float(deal.commission) if deal.commission is not None else None
            )
            != item.commission
            or (float(deal.swap) if deal.swap is not None else None) != item.swap
            or (
                deal.occurred_at.replace(tzinfo=UTC)
                if deal.occurred_at.tzinfo is None
                else deal.occurred_at.astimezone(UTC)
            )
            != item.occurred_at
        )
        deal.external_order_id = item.external_order_id
        deal.position_identifier = item.position_identifier
        deal.entry_type = item.entry_type
        deal.symbol = item.symbol.upper()
        deal.direction = item.direction.value
        deal.volume = item.volume
        deal.price = item.price
        deal.pnl = item.pnl
        deal.commission = item.commission
        deal.swap = item.swap
        deal.occurred_at = item.occurred_at
        if deal_changed:
            if previous_position_identifier:
                changed_position_ids.add(previous_position_identifier)
            if item.position_identifier:
                changed_position_ids.add(item.position_identifier)
        if is_new_deal:
            new_deals.append(deal)

    observed_positions: set[str] = set()
    previous_positions: dict[str, dict[str, object]] = {}
    for item in payload.positions:
        position_identifier = item.position_identifier or item.external_position_id
        observed_positions.add(position_identifier)
        position = db.scalar(
            select(MT5Position).where(
                MT5Position.account_id == account.id,
                MT5Position.external_position_id == position_identifier,
            )
        )
        if position is None:
            position = MT5Position(
                account_id=account.id,
                external_position_id=position_identifier,
            )
            db.add(position)
            changed_position_ids.add(position_identifier)
            previous_positions[position_identifier] = {}
        else:
            previous_positions[position_identifier] = {
                "volume": float(position.volume),
                "entry_price": (
                    float(position.entry_price) if position.entry_price is not None else None
                ),
                "stop_loss": (
                    float(position.stop_loss) if position.stop_loss is not None else None
                ),
                "take_profit": (
                    float(position.take_profit) if position.take_profit is not None else None
                ),
            }
        position.symbol = item.symbol.upper()
        position.direction = item.direction.value
        position.volume = item.volume
        position.entry_price = item.entry_price
        position.current_price = item.current_price
        position.stop_loss = item.stop_loss
        position.take_profit = item.take_profit
        position.floating_pnl = item.floating_pnl
        position.state = item.state
        position.observed_at = item.observed_at
        current_values = {
            "volume": item.volume,
            "entry_price": item.entry_price,
            "stop_loss": item.stop_loss,
            "take_profit": item.take_profit,
        }
        if previous_positions[position_identifier] != current_values:
            changed_position_ids.add(position_identifier)

    existing_positions = db.scalars(
        select(MT5Position).where(MT5Position.account_id == account.id)
    ).all()
    for position in existing_positions:
        if position.external_position_id not in observed_positions and position.state == "open":
            position.state = "closed"
            position.observed_at = payload.snapshot.observed_at
            changed_position_ids.add(position.external_position_id)

    snapshot = AccountSnapshot(
        account_id=account.id,
        balance=payload.snapshot.balance,
        equity=payload.snapshot.equity,
        margin=payload.snapshot.margin,
        free_margin=payload.snapshot.free_margin,
        observed_at=payload.snapshot.observed_at,
        source="mt5",
    )
    db.add(snapshot)
    db.flush()
    now = datetime.now(UTC)
    episodes_by_position: dict[str, Trade] = {}
    position_ids_to_reconcile = changed_position_ids | observed_positions
    for position_identifier in position_ids_to_reconcile:
        position = db.scalar(
            select(MT5Position).where(
                MT5Position.account_id == account.id,
                MT5Position.external_position_id == position_identifier,
            )
        )
        trade = reconcile_position_episode(
            db,
            account,
            position_identifier,
            position if position is not None and position.state == "open" else None,
            now,
        )
        position_changed = (
            position_identifier in changed_position_ids
            and previous_positions.get(position_identifier, {})
            != (
                {
                    "volume": float(position.volume),
                    "entry_price": (
                        float(position.entry_price)
                        if position.entry_price is not None
                        else None
                    ),
                    "stop_loss": (
                        float(position.stop_loss) if position.stop_loss is not None else None
                    ),
                    "take_profit": (
                        float(position.take_profit)
                        if position.take_profit is not None
                        else None
                    ),
                }
                if position is not None and position.state == "open"
                else {}
            )
        )
        if trade is not None and position_changed and not (
            trade.outcome != "open"
            and any(
                event.event_type == "position_closed"
                for event in db.scalars(
                    select(TradeEvent).where(TradeEvent.trade_id == trade.id)
                ).all()
            )
        ):
            db.add(
                TradeEvent(
                    trade_id=trade.id,
                    event_type="position_updated",
                    source="mt5",
                    payload={
                        "current": {
                            "volume": float(position.volume) if position else 0,
                            "entry_price": (
                                float(position.entry_price)
                                if position and position.entry_price is not None
                                else None
                            ),
                            "current_price": (
                                float(position.current_price)
                                if position and position.current_price is not None
                                else None
                            ),
                            "stop_loss": (
                                float(position.stop_loss)
                                if position and position.stop_loss is not None
                                else None
                            ),
                            "take_profit": (
                                float(position.take_profit)
                                if position and position.take_profit is not None
                                else None
                            ),
                            "floating_pnl": (
                                float(position.floating_pnl)
                                if position and position.floating_pnl is not None
                                else None
                            ),
                        },
                        "previous": previous_positions.get(position_identifier, {}),
                    },
                    occurred_at=now,
                )
            )
            episodes_by_position[position_identifier] = trade
        elif trade is not None:
            episodes_by_position[position_identifier] = trade
    for deal in new_deals:
        if deal.position_identifier is None:
            continue
        trade = episodes_by_position.get(deal.position_identifier)
        if trade is None:
            continue
        db.add(
            TradeEvent(
                trade_id=trade.id,
                event_type="execution_deal",
                source="mt5",
                payload={
                    "deal_id": deal.external_deal_id,
                    "order_id": deal.external_order_id,
                    "entry_type": deal.entry_type,
                    "direction": deal.direction,
                    "volume": float(deal.volume),
                    "price": float(deal.price),
                    "gross_pnl": float(deal.pnl) if deal.pnl is not None else None,
                    "commission": float(deal.commission) if deal.commission is not None else None,
                    "swap": float(deal.swap) if deal.swap is not None else None,
                },
                occurred_at=deal.occurred_at,
            )
        )
    run.status = "completed"
    run.records_processed = len(payload.orders) + len(payload.deals) + len(payload.positions) + 1
    run.completed_at = now
    connection = db.get(AccountConnection, account.id)
    if connection is None:
        raise HTTPException(status_code=503, detail="Account connection is unavailable")
    if connection.status != "disconnecting":
        connection.status = "connected"
    connection.last_synced_at = now
    connection.last_error = None
    db.commit()
    return {
        "sync_run_id": str(run.id),
        "status": run.status,
        "records_processed": run.records_processed,
    }


@router.post("/accounts/{account_id}/sync-failure")
def report_sync_failure(
    account: ConnectorAccount,
    payload: MT5SyncFailure,
    db: Database,
) -> dict[str, str]:
    run = db.scalar(
        select(SyncRun).where(
            SyncRun.id == payload.sync_run_id,
            SyncRun.account_id == account.id,
            SyncRun.status == "processing",
        )
    )
    if run is None:
        raise HTTPException(status_code=409, detail="Sync request is missing or no longer active")
    safe_error = payload.error.strip()[:2000]
    run.status = "failed"
    run.error = safe_error
    run.completed_at = datetime.now(UTC)
    connection = db.get(AccountConnection, account.id)
    if connection is None:
        raise HTTPException(status_code=503, detail="Account connection is unavailable")
    connection.status = "error"
    connection.last_error = safe_error
    db.commit()
    return {"sync_run_id": str(run.id), "status": run.status}
