import hashlib
import logging
import secrets
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, Database
from app.platform_models import (
    AccountConnection,
    AccountSnapshot,
    MT5Deal,
    MT5Order,
    MT5Position,
    SyncRun,
    TradingAccount,
)
from app.core.config import get_settings
from app.schemas import (
    AccountCreate,
    AccountList,
    AccountRename,
    AccountRead,
    MetaApiConnectRequest,
    MT5ConnectRequest,
)
from app.services.metaapi import (
    metaapi_client,
    provider_name,
    schedule_provision,
    schedule_sync,
)
from app.services import device as device_service
from app.services import ea as ea_service
from app.services.credentials import encrypt_secret
from app.services.mt5_method import effective_method

logger = logging.getLogger("tradeiq.accounts")

router = APIRouter(prefix="/accounts", tags=["Accounts"])


def get_owned_account(db: Database, user_id: UUID, account_id: UUID) -> TradingAccount:
    account_id_str = str(account_id)
    account = db.scalar(
        select(TradingAccount).where(
            TradingAccount.id == account_id_str,
            TradingAccount.user_id == user_id,
            TradingAccount.archived_at.is_(None),
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Trading account not found")
    return account


@router.get("", response_model=AccountList)
def list_accounts(
    current_user: CurrentUser,
    db: Database,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AccountList:
    accounts = db.scalars(
        select(TradingAccount)
        .where(
            TradingAccount.user_id == current_user.id,
            TradingAccount.archived_at.is_(None),
        )
        .order_by(TradingAccount.created_at.desc(), TradingAccount.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return AccountList(items=accounts, limit=limit, offset=offset)


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate, current_user: CurrentUser, db: Database
) -> TradingAccount:
    values = payload.model_dump()
    values["environment"] = payload.environment.value
    account = TradingAccount(
        user_id=current_user.id,
        **values,
    )
    db.add(account)
    db.flush()
    db.add(AccountConnection(account_id=account.id, connector_type="mt5", status="not_configured"))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this name already exists"
        ) from error
    db.refresh(account)
    return account


@router.get("/{account_id}/connection")
@router.get("/{account_id}/status")
def account_connection(
    account_id: UUID,
    current_user: CurrentUser,
    db: Database,
) -> dict[str, object]:
    account = get_owned_account(db, current_user.id, account_id)
    connection = db.get(AccountConnection, account.id)
    if connection is None:
        raise HTTPException(status_code=503, detail="Account connection status is unavailable")
    latest_run = db.scalar(
        select(SyncRun)
        .where(SyncRun.account_id == account.id)
        .order_by(SyncRun.started_at.desc())
        .limit(1)
    )
    last_synced_at = connection.last_synced_at
    if last_synced_at is not None and last_synced_at.tzinfo is None:
        last_synced_at = last_synced_at.replace(tzinfo=UTC)
    display_status = connection.status
    if (
        connection.connector_type == "ea"
        and display_status == "connected"
        and (last_synced_at is None or (datetime.now(UTC) - last_synced_at).total_seconds() > 600)
    ):
        display_status = "offline"
    snapshot = db.scalar(
        select(AccountSnapshot)
        .where(AccountSnapshot.account_id == account.id)
        .order_by(AccountSnapshot.observed_at.desc())
        .limit(1)
    )
    return {
        "account_id": str(account.id),
        "connector_type": connection.connector_type,
        "balance": float(snapshot.balance) if snapshot else None,
        "equity": float(snapshot.equity) if snapshot else None,
        "margin": float(snapshot.margin) if snapshot and snapshot.margin is not None else None,
        "currency": account.currency,
        "status": display_status,
        "last_synced_at": last_synced_at,
        "last_error": connection.last_error,
        "stale": (
            last_synced_at is None
            or (datetime.now(UTC) - last_synced_at).total_seconds() > 1800
        ),
        "latest_sync_run": (
            {
                "id": str(latest_run.id),
                "status": latest_run.status,
                "records_processed": latest_run.records_processed,
                "started_at": latest_run.started_at,
                "completed_at": latest_run.completed_at,
                "error": latest_run.error,
            }
            if latest_run
            else None
        ),
    }


@router.post("/{account_id}/metaapi/connect", status_code=status.HTTP_202_ACCEPTED)
async def connect_metaapi_account(
    account_id: UUID,
    payload: MetaApiConnectRequest,
    current_user: CurrentUser,
    db: Database,
) -> dict[str, object]:
    """Link the user's MT5 login via MetaApi, then import balance, positions and history."""
    if not get_settings().metaapi_token:
        raise HTTPException(
            status_code=503,
            detail="Live MT5 connections are not enabled on this server yet. Ask the platform admin to set METAAPI_TOKEN.",
        )
    account = get_owned_account(db, current_user.id, account_id)
    if effective_method(db, current_user) != "metaapi":
        raise HTTPException(
            status_code=403, detail="Your account is set up to connect with the Expert Advisor method."
        )
    connection = db.get(AccountConnection, account.id)
    if connection is None:
        raise HTTPException(status_code=503, detail="Account connection is unavailable")
    name = provider_name(str(account.id))
    spec = {
        "name": name,
        "type": "cloud-g2",
        "login": str(payload.login),
        "password": payload.password.get_secret_value(),
        "server": payload.server,
        "platform": "mt5",
        "magic": 0,
        "manualTrades": True,
    }
    account.external_account_id = str(payload.login)
    account.server_name = payload.server
    connection.connector_type = "metaapi"
    connection.status = "provisioning"
    connection.last_error = None
    connection.last_synced_at = None
    active = db.scalar(
        select(SyncRun.id).where(
            SyncRun.account_id == account.id, SyncRun.status.in_(["queued", "processing"])
        )
    )
    if active is None:
        db.add(SyncRun(account_id=account.id, status="queued"))
    db.commit()
    schedule_provision(str(account.id), spec)
    return {
        "account_id": str(account.id),
        "status": connection.status,
        "message": "Connecting to your broker. Balance, open positions and history will appear shortly.",
    }


@router.post("/{account_id}/metaapi/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_metaapi_account(
    account_id: UUID, current_user: CurrentUser, db: Database
) -> None:
    account = get_owned_account(db, current_user.id, account_id)
    connection = db.get(AccountConnection, account.id)
    if connection is not None and connection.connector_type == "ea":
        connection.connector_token_hash = None
        connection.status = "disconnected"
        db.commit()
        return
    if connection is None or not connection.provider_account_id:
        return
    try:
        api = metaapi_client()
        provider_account = await api.metatrader_account_api.get_account(
            connection.provider_account_id
        )
        await provider_account.remove()
    except Exception as error:
        raise HTTPException(
            status_code=502, detail="Could not remove the broker link. Try again."
        ) from error
    connection.provider_account_id = None
    connection.status = "disconnected"
    connection.last_error = None
    db.commit()


@router.post("/{account_id}/ea/connect", status_code=status.HTTP_201_CREATED)
def connect_ea_account(account_id: UUID, current_user: CurrentUser, db: Database) -> dict[str, object]:
    """Issue (or rotate) the webhook secret used by the TradeIQ Expert Advisor."""
    account = get_owned_account(db, current_user.id, account_id)
    if effective_method(db, current_user) != "ea":
        raise HTTPException(
            status_code=403, detail="Your account is set up to connect with the MT5 login method."
        )
    connection = db.get(AccountConnection, account.id)
    if connection is None:
        raise HTTPException(status_code=503, detail="Account connection is unavailable")
    connection.connector_type = "ea"
    connection.connector_token_hash = None
    connection.encrypted_password = None
    connection.provider_account_id = None
    connection.status = "pending"
    connection.last_error = None
    db.commit()
    # One per-user connector serves every login in the terminal; its secret is stable.
    url = device_service.device_url(str(current_user.id), device_service.issue_connector(db, current_user))
    return {
        "account_id": str(account.id),
        "status": connection.status,
        "already_installed": device_service.is_active(db, str(current_user.id)),
        "webhook_url": url,
        "installers": {os_name: f"{url}/installer/{os_name}" for os_name in ("mac", "windows")},
    }


@router.patch("/{account_id}", response_model=AccountRead)
def rename_account(
    account_id: UUID, payload: AccountRename, current_user: CurrentUser, db: Database
) -> TradingAccount:
    account = get_owned_account(db, current_user.id, account_id)
    account.name = payload.name.strip()
    db.commit()
    db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: UUID, current_user: CurrentUser, db: Database) -> None:
    """Permanently remove an account and its broker link. Journal trades are kept, unlinked."""
    account = get_owned_account(db, current_user.id, account_id)
    connection = db.get(AccountConnection, account.id)
    if connection is not None and connection.provider_account_id:
        try:
            provider_account = await metaapi_client().metatrader_account_api.get_account(
                connection.provider_account_id
            )
            await provider_account.remove()
        except Exception:
            logger.warning("Could not remove broker link for account %s", account.id, exc_info=True)
    db.delete(account)
    db.commit()


@router.post("/{account_id}/mt5/connect", status_code=status.HTTP_202_ACCEPTED)
def connect_mt5_account(
    account_id: UUID,
    payload: MT5ConnectRequest,
    current_user: CurrentUser,
    db: Database,
    response: Response,
) -> dict[str, object]:
    """Store MT5 login details so the worker can call mt5.login(login, password, server)."""
    account = get_owned_account(db, current_user.id, account_id)
    connection = db.get(AccountConnection, account.id)
    if connection is None:
        raise HTTPException(status_code=503, detail="Account connection is unavailable")
    token = secrets.token_urlsafe(48)
    account.external_account_id = str(payload.login)
    account.server_name = payload.server
    connection.connector_type = "mt5"
    connection.encrypted_password = encrypt_secret(payload.password.get_secret_value())
    connection.connector_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    connection.status = "pending"
    connection.last_error = None
    connection.sync_cursor = {"timeout": str(payload.timeout)}
    active = db.scalar(
        select(SyncRun).where(
            SyncRun.account_id == account.id, SyncRun.status.in_(["queued", "processing"])
        )
    )
    run = active
    if run is None:
        run = SyncRun(account_id=account.id, status="queued")
        db.add(run)
        db.flush()
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {
        "account_id": str(account.id),
        "status": connection.status,
        "sync_run_id": str(run.id),
        "login": payload.login,
        "server": payload.server,
        "connector_token": token,
        "message": "MT5 credentials saved. The MT5 worker will log in and import your history.",
    }


@router.delete("/{account_id}/mt5/connect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_mt5_account(account_id: UUID, current_user: CurrentUser, db: Database) -> None:
    account = get_owned_account(db, current_user.id, account_id)
    connection = db.get(AccountConnection, account.id)
    if connection is not None:
        connection.connector_token_hash = None
        connection.encrypted_password = None
        connection.status = "disconnected"
        connection.last_error = None
        db.commit()



@router.post("/{account_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def request_account_sync(
    account_id: UUID,
    current_user: CurrentUser,
    db: Database,
) -> dict[str, str]:
    account = get_owned_account(db, current_user.id, account_id)
    connection = db.get(AccountConnection, account.id)
    if connection is None or (
        connection.connector_token_hash is None and not connection.provider_account_id
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "connector_not_configured",
                "message": "Add the MT5 login, password and server before syncing.",
            },
        )
    if connection.connector_type == "ea":
        return {
            "sync_run_id": "",
            "status": "ea",
            "message": "The Expert Advisor pushes your data automatically while MT5 is open.",
        }
    active_run = db.scalar(
        select(SyncRun.id)
        .where(
            SyncRun.account_id == account.id,
            SyncRun.status.in_(["queued", "processing"]),
        )
        .limit(1)
    )
    if active_run is not None:
        if connection.provider_account_id:
            schedule_sync(str(account.id))
        return {
            "sync_run_id": str(active_run),
            "status": "queued",
            "message": "A sync is already in progress.",
        }
    run = SyncRun(account_id=account.id, status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)
    if connection.provider_account_id:
        schedule_sync(str(account.id))
    return {
        "sync_run_id": str(run.id),
        "status": run.status,
        "message": "Sync started.",
    }


@router.get("/{account_id}/history")
def account_history(
    account_id: UUID,
    current_user: CurrentUser,
    db: Database,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, list[dict[str, object]]]:
    account = get_owned_account(db, current_user.id, account_id)
    orders = db.scalars(
        select(MT5Order)
        .where(MT5Order.account_id == account.id)
        .order_by(MT5Order.occurred_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    deals = db.scalars(
        select(MT5Deal)
        .where(MT5Deal.account_id == account.id)
        .order_by(MT5Deal.occurred_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    positions = db.scalars(
        select(MT5Position)
        .where(MT5Position.account_id == account.id)
        .order_by(MT5Position.observed_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    snapshots = db.scalars(
        select(AccountSnapshot)
        .where(AccountSnapshot.account_id == account.id)
        .order_by(AccountSnapshot.observed_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "orders": [
            {
                "id": str(item.id),
                "external_order_id": item.external_order_id,
                "order_type": item.order_type,
                "volume": float(item.volume),
                "price": float(item.price) if item.price is not None else None,
                "state": item.state,
                "occurred_at": item.occurred_at,
                "source": item.source,
            }
            for item in orders
        ],
        "deals": [
            {
                "id": str(item.id),
                "external_deal_id": item.external_deal_id,
                "external_order_id": item.external_order_id,
                "symbol": item.symbol,
                "direction": item.direction,
                "volume": float(item.volume),
                "price": float(item.price),
                "pnl": float(item.pnl) if item.pnl is not None else None,
                "commission": float(item.commission) if item.commission is not None else None,
                "swap": float(item.swap) if item.swap is not None else None,
                "occurred_at": item.occurred_at,
                "source": item.source,
            }
            for item in deals
        ],
        "positions": [
            {
                "id": str(item.id),
                "external_position_id": item.external_position_id,
                "symbol": item.symbol,
                "direction": item.direction,
                "volume": float(item.volume),
                "state": item.state,
                "observed_at": item.observed_at,
                "source": item.source,
            }
            for item in positions
        ],
        "snapshots": [
            {
                "id": str(item.id),
                "balance": float(item.balance),
                "equity": float(item.equity),
                "margin": float(item.margin) if item.margin is not None else None,
                "free_margin": float(item.free_margin) if item.free_margin is not None else None,
                "observed_at": item.observed_at,
                "source": item.source,
            }
            for item in snapshots
        ],
    }


@router.get("/{account_id}/positions")
def account_positions(
    account_id: UUID,
    current_user: CurrentUser,
    db: Database,
) -> list[dict[str, object]]:
    account = get_owned_account(db, current_user.id, account_id)
    positions = db.scalars(
        select(MT5Position)
        .where(MT5Position.account_id == account.id, MT5Position.state == "open")
        .order_by(MT5Position.observed_at.desc(), MT5Position.external_position_id)
    ).all()
    return [
        {
            "position_identifier": position.external_position_id,
            "symbol": position.symbol,
            "direction": position.direction,
            "volume": float(position.volume),
            "entry_price": (
                float(position.entry_price) if position.entry_price is not None else None
            ),
            "current_price": (
                float(position.current_price) if position.current_price is not None else None
            ),
            "stop_loss": float(position.stop_loss) if position.stop_loss is not None else None,
            "take_profit": (
                float(position.take_profit) if position.take_profit is not None else None
            ),
            "floating_pnl": (
                float(position.floating_pnl) if position.floating_pnl is not None else None
            ),
            "observed_at": position.observed_at,
        }
        for position in positions
    ]
